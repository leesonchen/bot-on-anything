import time
import werobot
from config import channel_conf
from common import const
from common.log import logger
from channel.channel import Channel
from concurrent.futures import ThreadPoolExecutor
import requests
import io
import edge_tts
import asyncio

robot = werobot.WeRoBot(token=channel_conf(const.WECHAT_MP).get('token'))
thread_pool = ThreadPoolExecutor(max_workers=8)

@robot.text
def handle_text(msg):
    logger.info(f'[WX_Public] receive public msg: {msg.content}, userId: {msg.source}')
    return WechatServiceAccount().handle(msg)

@robot.voice
def handle_voice(msg):
    logger.info(f'[WX_Public] receive public voice msg: {msg.recognition}, userId: {msg.source}, type: {msg.__type__}, mediaId:{msg.media_id}, format:{msg.format}')
    msg.content = None
    return WechatServiceAccount().handle(msg)

class WechatServiceAccount(Channel):
    wait_response = False

    def startup(self):
        logger.info('[WX_Public] Wechat Public account service start!')
        robot.config['PORT'] = channel_conf(const.WECHAT_MP).get('port')
        robot.config["APP_ID"] = channel_conf(const.WECHAT_MP).get('app_id')
        robot.config["APP_SECRET"] = channel_conf(const.WECHAT_MP).get('app_secret')
        robot.config['HOST'] = '0.0.0.0'
        robot.run()

    def handle(self, msg, count=0):
        context = {}
        context['from_user_id'] = msg.source
        context['msg_type'] = msg.__type__
        context['msg'] = msg
        self.wait_response = True
        thread_pool.submit(self._do_send, msg.content, context)

        # wait 5 seconds
        while self.wait_response and count < 4:
            # sleep one second
            time.sleep(1)
            count += 1
            print('waiting count: {}'.format(count))

        if self.wait_response:
            return "正在思考中..."

        return ""

    def make_image_reply(self, client, reply_text, user_id):
        url = reply_text[0]
        pic_res = requests.get(url, stream=True)
        # 将图片下载保存到本地
        file_name = f"download/{user_id}_{int(time.time())}.png"
        with open(file_name, 'wb') as f:
            for chunk in pic_res.iter_content(chunk_size=1024):
                f.write(chunk)

        file_obj = open(file_name, 'rb')
        upload_res = client.upload_media('image', file_obj)
        media_id = upload_res['media_id']
        print(f"upload_res: {upload_res}, media_id: {media_id}")
        client.send_image_message(user_id, media_id)

    def make_voice_reply(self, client, reply_text, user_id):
        file_name = f"download/{user_id}_{int(time.time())}.mp3"
        #voice = 'zh-CN-YunxiNeural'
        #voice = 'zh-CN-XiaoyiNeural'

        voice = 'zh-CN-XiaoxiaoNeural'
        rate = '-0%'
        volume = '+0%'
        asyncio.run(self.save_tts_file(voice, rate, volume, reply_text, file_name))
        file_obj = open(file_name, 'rb')
        upload_res = client.upload_media('voice', file_obj)
        media_id = upload_res['media_id']
        print(f"upload_res: {upload_res}, media_id: {media_id}")
        client.send_voice_message(user_id, media_id)

    def voice_to_text(self, client, msg):
        if msg.recognition is not None:
            return msg.recognition
        else:
            voice_res = client.download_media(msg.media_id)
            file_name = f"download/0_{msg.source}_{int(time.time())}.{msg.format}"
            with open(file_name, 'wb') as f:
                for chunk in voice_res.iter_content(chunk_size=1024):
                    f.write(chunk)

            # openai的whisper模型不支持amr格式
            if msg.format == 'amr':
                from pydub import AudioSegment
                outfile = file_name.replace('amr', 'wav')
                AudioSegment.from_file(file_name).export(outfile, format = 'wav')
                file_name = outfile

            audio_file = open(file_name, "rb")

            from model.openai.open_ai_model import OpenAIModel
            openai_robot = OpenAIModel()
            transcript = openai_robot.voice_recognition(audio_file)
            if transcript is None or not transcript.get("text"):
                return None

            transcript = transcript.get("text")
            logger.info(f'transcript={transcript}')
            return transcript

    async def save_tts_file(self, voice, rate, volume, text, filename):
        tts = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
        await tts.save(filename)

    def _do_send(self, query, context):
        try:
            client = robot.client

            if context.get('msg_type', None) == 'voice':
                query = self.voice_to_text(client, context['msg'])
                logger.info(f"query: {query}")
                if query is None:
                    client.send_text_message(context['from_user_id'], "抱歉我听不清楚，请用标准普通话再说一遍")
                    return

            if query.startswith("画"):
                context['type'] = 'IMAGE_CREATE'
                query = query[1:].strip()

            reply_text = super().build_reply_content(query, context)
            self.wait_response = False

            logger.info('[WX_Public] reply content: {}'.format(reply_text))

            if context.get('type', None) == 'IMAGE_CREATE':
                self.make_image_reply(client, reply_text, context['from_user_id'])
            else:
                if context.get('msg_type', None) == 'voice':
                    self.make_voice_reply(client, reply_text, context['from_user_id'])
                else:
                    client.send_text_message(context['from_user_id'], reply_text)

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(traceback.format_exc())