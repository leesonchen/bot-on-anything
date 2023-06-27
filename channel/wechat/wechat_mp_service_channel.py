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
import string

robot = werobot.WeRoBot(token=channel_conf(const.WECHAT_MP).get('token'))
thread_pool = ThreadPoolExecutor(max_workers=8)

zh_punctuation_str = '《》【】（）。、‘’“”：；！？·，'   #中文符号
extended_punctuation = f'{zh_punctuation_str}{string.punctuation}{string.whitespace}'  #中英文符号
extended_seperator = '。、‘’“”：；！？，\'\":;,.!?'  #中英文分隔符

def is_Chinese(text):
    # 增加对中英混合的情况，如果大部分内容都是中文，则认为是中文
    zh_count = 0
    en_count = 0
    for ch in text:
        # print(f'{ch}|{ord(ch)}')
        if is_en_extended(ch):
            en_count += 1
        elif is_zh_extended(ch):
            zh_count += 1
        else:
            # 非中文非英文字符，直接返回False
            return False

    return zh_count > 0

def is_English(text):
    for ch in text:
        if not is_en_extended(ch):
            return False
    return True

def is_Japanese(text):
    for ch in text:
        if is_jp(ch):
            return True
    return False

def is_zh_extended(w):
    if '\u4e00' <= w <= '\u9fff' or w.isdigit() or w in extended_punctuation:
        return True

def is_zh(w):
    if '\u4e00' <= w <= '\u9fff':
        return True

def is_zh_punctuation(w):
    if w in zh_punctuation_str:
        return True

def is_en(w):
    if 'a'<=w<='z' or 'A'<=w<='Z':
        return True

def is_en_punctuation(w):
    if w in string.punctuation:
        return True

def is_en_extended(w):
    if is_en(w) or w.isdigit() or w in extended_punctuation:
        return True

def is_jp(w):
    if ('\u3040' <= w <= '\u309f') or ('\u30A0' <= w <= '\u30ff'):
        return True

def is_jp_extended(w): #extended指不满足条件肯定不是日文
    if ('\u3040' <= w <= '\u309f') or ('\u30A0' <= w <= '\u30ff') or ('\u4e00' <= w <= '\u9fbf') or w.isdigit() or w in extended_punctuation:
        return True


@robot.text
def handle_text(msg):
    logger.info(f'[WX_Public] receive public msg: {msg.content}, userId: {msg.source}')
    return WechatServiceAccount().handle(msg)

@robot.voice
def handle_voice(msg):
    logger.info(f'[WX_Public] receive public voice msg: {msg.recognition}, userId: {msg.source}, type: {msg.__type__}, mediaId:{msg.media_id}, format:{msg.format}')
    msg.content = msg.recognition
    return WechatServiceAccount().handle(msg)

class WechatServiceAccount(Channel):
    wait_response = False
    voice_map = {}
    langList = ''

    def isSensitive(self, text):
        with open('sensitive_words.txt', 'r', encoding='utf-8') as f: #加入检测违规词
            sensitive_words = [line.strip() for line in f.readlines()]
            found = False
            for word in sensitive_words:
                if word != '' and word in text:
                    found = True
                    break
            return found

    def readVoicename(self):
        with open('voice_name.txt', 'r', encoding='utf-8') as f:
            voice_name = [line.strip() for line in f.readlines()]
            for name in voice_name:
                nameSplits = name.split('-')
                lang = nameSplits[0] + '-' + nameSplits[1]
                self.voice_map[lang] = nameSplits[2]
                self.langList = self.langList + lang + ' '

        logger.info(f'langList: {self.langList}')

    def startup(self):
        logger.info('[WX_Public] Wechat Public account service start!')
        robot.config['PORT'] = channel_conf(const.WECHAT_MP).get('port')
        robot.config["APP_ID"] = channel_conf(const.WECHAT_MP).get('app_id')
        robot.config["APP_SECRET"] = channel_conf(const.WECHAT_MP).get('app_secret')
        robot.config['HOST'] = '0.0.0.0'
        robot.run()

    def handle(self, msg, count=0):
        if self.isSensitive(msg.content):
            return "抱歉该话题不适合讨论"

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

    # search keyword in voice_map
    def searchVoice(self, keyword):
        for key in self.voice_map.keys():
            if keyword in key:
                voice = key + '-' +  self.voice_map[key]
                return voice
        return None

    def suitableVoice(self, text):
        self.readVoicename()

        if is_Japanese(text):
            voice =  self.searchVoice('ja-JP')
            print(f"voice: {voice}")
            return voice
        elif is_Chinese(text):
            voice =  self.searchVoice('zh-CN')
            print(f"voice: {voice}")
            return voice
        elif is_English(text):
            # voice = 'en-US-AnaNeural'
            voice =  self.searchVoice('en-US')
            print(f"voice: {voice}")
            return voice

        from model.openai.chatgpt_model import ChatGPTModel
        robot = ChatGPTModel()
        query = f"considering {self.langList}, which of the above language code can be best described for the following text :{text}"
        print(f"query: {query}")
        if len(query) > 1000:
            query = query[:1000]

        session = []
        user_item = {'role': 'user', 'content': query}
        session.append(user_item)

        rep = robot.reply_text(session)
        print(f"rep: {rep}")

        for lang in self.voice_map:
            if lang in rep:
                return lang + '-' + self.voice_map[lang]

        return 'zh-CN-XiaoxiaoNeural'

    def make_voice_reply(self, client, reply_text, user_id, voice='zh-CN-XiaoxiaoNeural', rate='-0%', volume='+0%', advancedMode=True, with_text=True):
        #voice = 'zh-CN-YunxiNeural'
        #voice = 'zh-CN-XiaoyiNeural'

        if advancedMode:
            voice = self.suitableVoice(reply_text)
            print(f"voice: {voice}")

        seperateNum = 300
        while len(reply_text) > 0:
            # if len(reply_text) > 300:
            current_text = reply_text[:seperateNum]
            reply_text = reply_text[seperateNum:]
            try:
                self.make_single_voice_reply(client, current_text, user_id, voice, rate, volume, with_text)
            except Exception as e:
                logger.warn(f'[WX_Public] make_voice_reply error: {e}')
                errstr = str(e)
                if 'playtime' in errstr:
                    seperateNum = seperateNum - 50
                    reply_text = current_text + reply_text
                else:
                    raise e

    # 单段语音输出
    def make_single_voice_reply(self, client, reply_text, user_id, voice='zh-CN-XiaoxiaoNeural', rate='-0%', volume='+0%', with_text=True):
        file_name = f"download/{user_id}_{int(time.time())}.mp3"
        asyncio.run(self.save_tts_file(voice, rate, volume, reply_text, file_name))
        file_obj = open(file_name, 'rb')

        upload_res = client.upload_media('voice', file_obj)
        media_id = upload_res['media_id']
        print(f"upload_res: {upload_res}, media_id: {media_id}")
        client.send_voice_message(user_id, media_id)
        if with_text:
            client.send_text_message(user_id, reply_text)

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