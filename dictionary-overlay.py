import asyncio
import time
import json
import re
import sys
import os
from pathlib import Path
import websocket_bridge_python
from tokenizers import Tokenizer
from tokenizers.models import BPE
from tokenizers.pre_tokenizers import Whitespace
from tokenizers.trainers import BpeTrainer
from playwright.async_api import Playwright, async_playwright, Page
from threading import Timer

page: Page = None
playwright: Playwright

dictionary = {}
dictionary_file_path = os.path.join(sys.path[0], "dictionary.json")
knownwords_file_path = os.path.join(sys.path[0], "knownwords.txt")
unknownwords_file_path = os.path.join(sys.path[0], "unknownwords.txt")
dictionary_file = Path(dictionary_file_path)
if dictionary_file.is_file():
    # file exists
    with open(dictionary_file_path, "r") as f:
        dictionary = json.load(f)

known_words = set(open(knownwords_file_path).read().split())
unknown_words = set(open(unknownwords_file_path).read().split())


async def launch_deepl():
    global playwright
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context()
    global page
    page = await context.new_page()
    await page.goto("https://www.deepl.com/translator")


async def translate(word):
    content = word
    if page == None:
        await launch_deepl()
    await page.eval_on_selector(".lmt__target_textarea", "el => el.value = ''")
    await page.eval_on_selector(
        ".lmt__source_textarea", "(el, content) => el.value = content", content
    )
    await page.type(".lmt__source_textarea", "\n")

    await page.wait_for_function(
        'document.querySelector(".lmt__target_textarea").value != ""'
    )
    return await page.eval_on_selector(".lmt__target_textarea", "el => el.value.trim()")


async def parse(sentence):
    only_unknown_words = await bridge.get_emacs_var("dictionary-overlay-just-unknown-words")
    tokenizer = Tokenizer(BPE())
    pre_tokenizer = Whitespace()
    tokens = pre_tokenizer.pre_tokenize_str(sentence)
    if only_unknown_words == 'true':
        print(1)
        tokens = [token for token in tokens if token[0].lower() in unknown_words]
    else:
        tokens = [token for token in tokens if new_word_p(token[0].lower())]
    return tokens


def new_word_p(word):
    if len(word) < 3:
        return False
    if re.match(r"[\W\d]", word, re.M | re.I):
        return False
    return word not in known_words


def dump_knownwords_to_file():
    with open(knownwords_file_path, "w") as f:
        for word in known_words:
            f.write(f"{word}\n")
            
def dump_unknownwords_to_file():
    with open(unknownwords_file_path, "w") as f:
        for word in unknown_words:
            f.write(f"{word}\n")
 

def snapshot():
    dump_dictionary_to_file()
    dump_knownwords_to_file()
    dump_unknownwords_to_file()
    Timer(10, snapshot).start()


def dump_dictionary_to_file():
    with open(dictionary_file_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=4)


# dispatch message recived from Emacs.
async def on_message(message):
    info = json.loads(message)
    cmd = info[1][0].strip()
    sentenceStr = info[1][1]
    point = info[1][2]
    if cmd == "render":
        await render(sentenceStr)
    elif cmd == "jump_next_unkown_word":
        await jump_next_unkown_word(sentenceStr, point)
    elif cmd == "jump_prev_unkown_word":
        await jump_prev_unkown_word()
    elif cmd == "mark_word_know":
        word = info[1][3]
        if word in unknown_words:
            unknown_words.remove(word)
        known_words.add(word)
    elif cmd == "mark_word_unknow":
        word = info[1][3]
        if word in known_words:
            known_words.remove(word)
        unknown_words.add(word)
    else:
        print("not fount handler for {cmd}".format(cmd=cmd), flush=True)


async def jump_next_unkown_word(sentenceStr, point):
    tokens = await parse(sentenceStr)
    # todo: write this with build-in 'any' function
    for token in tokens:
        begin = token[1][0] + 1
        if point < begin:
            cmd = "(goto-char {begin})".format(begin=begin)
            await run_and_log(cmd)
            break


async def render(message):
    try:
        tokens = await parse(message)
        for token in tokens:
            word = token[0].lower()
            chinese: str
            if word in dictionary:
                chinese = dictionary[word]
            else:
                chinese = await translate(word)
                dictionary[word] = chinese
            await render_word(token, chinese)
    except Exception as e:
        print(e)


async def render_word(token, chinese):
    word = token[0]
    display = "{en}({zh})".format(en=word, zh=chinese)
    begin = token[1][0] + 1
    end = token[1][1] + 1
    cmd = '(dictionary-add-overlay-from {begin} {end} "{word}" "{display}")'.format(
        begin=begin, end=end, word=word, display=display
    )
    await run_and_log(cmd)


# eval in emacs and log the command.
async def run_and_log(cmd):
    print(cmd, flush=True)
    await bridge.eval_in_emacs(cmd)


async def main():
    snapshot()
    global bridge
    bridge = websocket_bridge.bridge_app_regist(on_message)
    #await launch_deepl()
    await bridge.start()


asyncio.run(main())