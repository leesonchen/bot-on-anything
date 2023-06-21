import time
import werobot
from config import channel_conf
from common import const
from common.log import logger
from channel.channel import Channel
from concurrent.futures import ThreadPoolExecutor
import requests
import io
import pyttsx4


robot = werobot.WeRoBot(token=channel_conf(const.WECHAT_MP).get('token'))
thread_pool = ThreadPoolExecutor(max_workers=8)
engine = pyttsx4.init()
voices = engine.getProperty('voices')
for voice in voices:
    print(voice)

@robot.text
def hello_world(msg):
    logger.info('[WX_Public] receive public msg: {}, userId: {}'.format(msg.content, msg.source))
    logger.info(f'[WX_Public] receive public msg: {msg}')
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

    def _do_send(self, query, context):
        if query.startswith("画"):
            context['type'] = 'IMAGE_CREATE'
            query = query[1:].strip()

        reply_text = super().build_reply_content(query, context)
        self.wait_response = False

        logger.info('[WX_Public] reply content: {}'.format(reply_text))

        client = robot.client
        try:
            if context.get('type') and context['type'] == 'IMAGE_CREATE':
                url = reply_text[0]
                pic_res = requests.get(url, stream=True)
                # 将图片下载保存到本地
                file_name = f"download/{context['from_user_id']}_{int(time.time())}.png"
                with open(file_name, 'wb') as f:
                    for chunk in pic_res.iter_content(chunk_size=1024):
                        f.write(chunk)

                file_obj = open(file_name, 'rb')
                upload_res = client.upload_media('image', file_obj)
                media_id = upload_res['media_id']
                print(f"upload_res: {upload_res}, media_id: {media_id}")
                client.send_image_message(context['from_user_id'], media_id)
            else:
                client.send_text_message(context['from_user_id'], reply_text)

                file_name = f"download/{context['from_user_id']}_{int(time.time())}.mp3"
                engine.save_to_file(reply_text, file_name)
                engine.runAndWait()

                file_obj = open(file_name, 'rb')
                upload_res = client.upload_media('voice', file_obj)
                media_id = upload_res['media_id']
                print(f"upload_res: {upload_res}, media_id: {media_id}")
                client.send_voice_message(context['from_user_id'], media_id)

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(traceback.format_exc())

    def _do_send_img(self, query, context):
        logger.info(f'[_do_send_img] : query={query}')
        try:
            if not query:
                return
            reply_user_id=context['from_user_id']
            img_urls = super().build_reply_content(query, context)
            self.wait_response = False
            if not img_urls:
                logger.info('无法生成图片')
                return
            if not isinstance(img_urls, list):
                self.send(img_urls, reply_user_id)
                return
            for url in img_urls:
            # 图片下载
                pic_res = requests.get(url, stream=True)
                image_storage = io.BytesIO()
                for block in pic_res.iter_content(1024):
                    image_storage.write(block)
                image_storage.seek(0)

                # 图片发送
                logger.info('[WX] sendImage, receiver={}'.format(reply_user_id))
                return '发送图片中...'
        except Exception as e:
            import traceback
            # traceback.print_exc()
            logger.error(traceback.format_exc())
