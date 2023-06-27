import time
import werobot
from config import channel_conf
from common import const
from common.log import logger
from channel.channel import Channel
from concurrent.futures import ThreadPoolExecutor
import requests
import edge_tts
import asyncio
import string
import threading

robot = werobot.WeRoBot(token=channel_conf(const.WECHAT_MP).get('token'))
thread_pool = ThreadPoolExecutor(max_workers=8)
voice_map = {}
langList = ''
zh_punctuation_str = '《》【】（）。、‘’“”：；！？·，'   #中文符号
extended_punctuation = f'{zh_punctuation_str}{string.punctuation}{string.whitespace}'  #中英文符号
extended_seperator = '。、‘’“”：；！？，\'\":;,.!?'  #中英文分隔符

@robot.text
def handle_text(msg):
    logger.info(f'[WX_Public] receive public msg: {msg.content}, userId: {msg.source}')
    return WechatServiceAccount().handle(msg)

@robot.voice
def handle_voice(msg):
    logger.info(f'[WX_Public] receive public voice msg: {msg.recognition}, userId: {msg.source}, type: {msg.__type__}, mediaId:{msg.media_id}, format:{msg.format}')
    msg.content = msg.recognition
    return WechatServiceAccount().handle(msg)

@robot.subscribe
def handle_subscribe(msg):
    logger.info(f'[WX_Public] receive public subscribe msg: {msg}, userId: {msg.source}, type: {msg.__type__}')
    # return f"{msg.target}:{msg.source}, 终于等到你！欢迎关注~"
    return "终于等到你！欢迎关注~"

@robot.unsubscribe
def handle_unsubscribe(msg):
    logger.info(f'[WX_Public] receive public unsubscribe msg: {msg}, userId: {msg.source}, type: {msg.__type__}')
    return "青山不改，绿水长流。后会有期【抱拳】~"


# @robot.key_click("V1001_AI_CHAT")
# def handle_menu_ai_chat(msg):
#     logger.info(f'[WX_Public] receive handle_menu_click target: {msg.target}, source: {msg.source}, key:{msg.key}, type: {msg.__type__}')
#     res = robot.client.delete_menu()
#     logger.info(f'[WX_Public] delete menu res: {res}')
#     return f"{msg.source} 点击了: {msg.key}"

# @robot.click
# def handle_menu_click(msg):
#     logger.info(f'[WX_Public] receive handle_menu_click target: {msg.target}, source: {msg.source}, key:{msg.key}, type: {msg.__type__}')
#     return f"你点击了: {msg.key}"

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


class WechatServiceAccount(Channel):
    wait_response = False

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
        global voice_map, langList
        with open('voice_name.txt', 'r', encoding='utf-8') as f:
            voice_name = [line.strip() for line in f.readlines()]
            for name in voice_name:
                nameSplits = name.split('-')
                lang = nameSplits[0] + '-' + nameSplits[1]
                voice_map[lang] = nameSplits[2]
                langList = langList + lang + ' '

        logger.info(f'langList: {langList}')

    def createMenu(self):
        res = robot.client.create_menu({
                        "button":[
                            {
                                "type":"click",
                                "name":"AI助手",
                                "key":"V1001_AI_CHAT"
                            },
                            {
                                "name":"口语练习",
                                "sub_button":[
                                    {
                                        "type":"click",
                                        "name":"英语对话",
                                        "key":"V2001_ENGLISH"
                                    },
                                    {
                                        "type":"click",
                                        "name":"韩语对话",
                                        "key":"V2002_KOREAN"
                                    }
                                ]
                            },
                            {
                                "name":"我的",
                                "sub_button":[
                                    {
                                        "type":"click",
                                        "name":"每日签到",
                                        "key":"V3001_CHECKIN"
                                    },
                                    {
                                        "type":"click",
                                        "name":"我的积分",
                                        "key":"V3002_ACCOUNT"
                                    },
                                    {
                                        "type":"click",
                                        "name":"赞一下我们",
                                        "key":"V3003_GOOD"
                                    }
                                ]
                            }
                        ]})

    def startup(self):
        logger.info('[WX_Public] Wechat Public account service start!')
        robot.config['PORT'] = channel_conf(const.WECHAT_MP).get('port')
        robot.config["APP_ID"] = channel_conf(const.WECHAT_MP).get('app_id')
        robot.config["APP_SECRET"] = channel_conf(const.WECHAT_MP).get('app_secret')
        robot.config['HOST'] = '0.0.0.0'
        self.readVoicename()
        # self.createMenu()
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

        # wait 4 seconds
        while self.wait_response and count < 9:
            # sleep one second
            time.sleep(0.5)
            count += 1
            print('waiting count: {}'.format(count))

        if self.wait_response:
            return "[正在思考中...]"

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
        global voice_map
        for key in voice_map.keys():
            if keyword in key:
                voice = key + '-' + voice_map[key]
                return voice
        return None

    def suitableVoice(self, text):
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

        global voice_map, langList

        from model.openai.chatgpt_model import ChatGPTModel
        robot = ChatGPTModel()
        query = f"considering {langList}, which of the above language code can be best described for the following text:{text}"
        print(f"query: {query}")
        if len(query) > 1000:
            query = query[:1000]

        session = []
        user_item = {'role': 'user', 'content': query}
        session.append(user_item)

        rep = robot.reply_text(session)
        print(f"rep: {rep}")

        voice = 'zh-CN-XiaoxiaoNeural'
        for lang in voice_map:
            if lang in rep:
                voice = lang + '-' + voice_map[lang]
                break

        print(f"voice: {voice}")
        return voice

    def seperateText(self, text):
        words = []
        seperators = []
        oneWord = ''
        for ch in text:
            if ch in extended_seperator:
                seperators.append(ch)
                words.append(oneWord)
                oneWord = ''
            else:
                oneWord = oneWord + ch
        if oneWord != '':
            words.append(oneWord)
        print(f"words: {len(words)}, seperators: {len(seperators)}")
        return words, seperators

    def isJapaneseVoice(self, voice):
        if (voice is not None) and ('ja-JP-' in voice):
            return True
        return False

    def isEnglishVoice(self, voice):
        if (voice is not None) and ('en-' in voice):
            return True
        return False

    def make_voice_reply(self, client, reply_text, user_id, voice='zh-CN-XiaoxiaoNeural', rate='-0%', volume='+0%', with_text=True, seperateNum = 280, advancedMode = False):
        if advancedMode:
            voice = None
        else:
            voice = self.suitableVoice(reply_text)

        orig_text = reply_text
        words, seperators = self.seperateText(reply_text)

        current_text = ''
        currentLen = 0
        inChineseMode = None
        modeChanged = False

        try:
            for i in range(len(words)):
                maxLen = seperateNum
                word = words[i].strip()
                if is_English(word):
                    maxLen = 2.2 * seperateNum

                if i < len(seperators):
                    word = word + seperators[i]

                lword = len(word)
                if lword <= 1:
                    current_text = current_text + word
                    currentLen = currentLen + lword
                    continue

                if currentLen + lword < maxLen:    # 1是分隔符
                    if advancedMode:    # 高级模式需要处理多语言混杂情况
                        # 判断中文状态是否发生变化
                        if is_Chinese(word):
                            if inChineseMode == None:
                                inChineseMode = True
                            elif inChineseMode == False:
                                # 排除日文夹带汉字的情况
                                if (not self.isJapaneseVoice(voice)) or (seperators[i-1] in '：。！？:!?'):
                                    modeChanged = True
                                    inChineseMode = True
                        else:
                            if inChineseMode == None:
                                inChineseMode = False
                            elif inChineseMode == True:
                                if (not is_English(word)) or (lword > 10):  # 中文里面夹着少量英文，直接忽略语言切换
                                    modeChanged = True
                                    inChineseMode = False

                    if modeChanged:
                        # 中文外文切换，先处理之前的内容
                        modeChanged = False
                        print(f"modeChanged: currentLen: {currentLen}; current word:{word}; voice:{voice}; inChineseMode:{inChineseMode}")
                        self.make_single_voice_reply(client, current_text, user_id, voice, rate, volume, with_text)
                        voice = self.suitableVoice(word)
                        print(f"current voice:{voice}")
                        current_text = word
                        currentLen = lword
                    else:
                        currentLen = currentLen + lword # 1是空格
                        current_text = current_text + word

                else:   # 增加1个短词则超过字数
                    print(f"currentLen: {currentLen}; current word: {word}; maxLen: {maxLen}; voice:{voice}; inChineseMode:{inChineseMode}")

                    if currentLen == 0: # 一个词都放不下，需要硬处理
                        while len(word) > maxLen:
                            current_text = word[:maxLen]
                            word = word[maxLen:]
                            if voice is None:
                                voice = self.suitableVoice(current_text)
                            self.make_single_voice_reply(client, current_text, user_id, voice, rate, volume, with_text)

                        lword = len(word)
                    else:
                        if voice is None:
                            voice = self.suitableVoice(current_text)
                        self.make_single_voice_reply(client, current_text, user_id, voice, rate, volume, with_text)
                    current_text = word
                    currentLen = lword
                    inChineseMode = is_Chinese(word)
                    modeChanged = False

            if currentLen > 0:
                self.make_single_voice_reply(client, current_text, user_id, voice, rate, volume, with_text)
        except Exception as e:
            logger.warn(f'[WX_Public] make_voice_reply error: {e}')
            errstr = str(e)
            if 'playtime' in errstr:    # 语音长度超过限制
                logger.warn(f'playtime error, use: {seperateNum - 50}')
                self.make_voice_reply(client, orig_text, user_id, voice, rate, volume, with_text, seperateNum - 50, advancedMode)
            else:
                raise e

    # 单段语音输出
    def make_single_voice_reply(self, client, reply_text, user_id, voice='zh-CN-XiaoxiaoNeural', rate='-0%', volume='+0%', with_text=True, retry_count=0):
        if voice is None:
            voice = self.suitableVoice(reply_text)

        file_name = f"download/{user_id}_{int(time.time())}.mp3"
        if self.isEnglishVoice(voice):
            rate = '-20%'
        asyncio.run(self.save_tts_file(voice, rate, volume, reply_text, file_name))
        file_obj = open(file_name, 'rb')

        try:
            upload_res = client.upload_media('voice', file_obj)
        except Exception as e:
            errstr = str(e)
            if 'media data missing' in errstr and retry_count < 1:
                # 声音无效
                if voice != 'zh-CN-XiaoxiaoNeural':
                    voice = 'zh-CN-XiaoxiaoNeural'
                else:
                    voice = self.suitableVoice('incorrect language, please try again.' + reply_text)
                self.make_single_voice_reply(client, reply_text, user_id, voice, rate, volume, with_text, retry_count + 1)
            elif 'playtime' in errstr:    # 语音长度超过限制
                raise e
            else:
                import traceback
                traceback.print_exc()
                client.send_text_message(user_id, '[暂时无法生成语音]\r\n' + reply_text)

            self.wait_response = False
            return

        media_id = upload_res['media_id']
        print(f"upload_res: {upload_res}, media_id: {media_id}")
        client.send_voice_message(user_id, media_id)
        self.wait_response = False
        if with_text:
            client.send_text_message(user_id, reply_text)

    def voice_to_text(self, client, msg, wechatModeOnly=False):
        if wechatModeOnly:
            return msg.recognition

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

    def check_progress(self, client, user_id):
        if self.wait_response:
            client.send_text_message(user_id, '[努力思考中...]')

    def _do_send(self, query, context):
        try:
            client = robot.client

            if context.get('msg_type', None) == 'voice':
                query = self.voice_to_text(client, context['msg'])
                logger.info(f"query: {query}")
                if query is None:
                    client.send_text_message(context['from_user_id'], "抱歉我听不清楚，请用标准普通话再说一遍")
                    self.wait_response = False
                    return
                # client.send_text_message(context['from_user_id'], f"[听到：{query}]")

            if query.startswith("画"):
                context['type'] = 'IMAGE_CREATE'
                # query = query[1:].strip()

            # timer = None
            # if self.wait_response:
            #     timer = threading.Timer(20, self.check_progress, args=(client, context['from_user_id']))
            #     timer.start()

            reply_text = super().build_reply_content(query, context)
            # logger.info('[WX_Public] reply content: {}'.format(reply_text))

            if context.get('type', None) == 'IMAGE_CREATE':
                self.make_image_reply(client, reply_text, context['from_user_id'])
            else:
                if context.get('msg_type', None) == 'voice':
                    self.make_voice_reply(client, reply_text, context['from_user_id'], with_text=False)
                    client.send_text_message(context['from_user_id'], f'[听到：{query}]\r\n{reply_text}')
                else:
                    client.send_text_message(context['from_user_id'], reply_text)

            self.wait_response = False
            # if timer is not None:
            #     timer.cancel()

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(traceback.format_exc())
