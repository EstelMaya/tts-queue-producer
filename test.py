from aiohttp import ClientSession, ClientTimeout
import asyncio
from argparse import ArgumentParser
from os import makedirs
from shutil import rmtree

parser = ArgumentParser()
parser.add_argument("-n", "--num", default=1, type=int)
parser.add_argument("-u", "--url", default="http://localhost")
parser.add_argument("-c", "--clear", action='store_true')
parser.add_argument("-f", "--format", default='mp3')
parser.add_argument("-p", "--port")

args = parser.parse_args()
NUM = args.num
URL = args.url
PORT = ":"+args.port if args.port else ""
CLEAR = args.clear
FORMAT = args.format

msg = {
    "format": FORMAT,
    "data": [{
        "type": "text",
        "lang": "ru",
        "speaker": "Michael",
        "data": [{
              "text": "В первую очередь квазары были определены как объекты с большим красным смещением, имеющие электромагнитное излучение (включая радиоволны и видимый свет) и исследования по обнаружению квазаров показали, что в далеком прошлом активность квазаров была более распространенной.",
              "emotion": [7],
            "pauseAfter": 300,
            "pauseBefore": 0}]}]}



async def post(session, i):
    async with session.post(f'{URL}{PORT}/synth', json=msg, ssl=False) as r:
        print(r.status)
        print(r.content_type)
        if r.status == 200:
            with open(f'out/{i}.{FORMAT}', 'wb+') as f:
                # pcm is used for realtime
                if FORMAT == 'pcm':
                    while (chunk := await r.content.read(2**10)):
                        f.write(chunk)
                else:
                    f.write(await r.content.read())


async def main(num):
    async with ClientSession(timeout=ClientTimeout(total=0)) as session:
        await asyncio.gather(*[post(session, i) for i in range(num)])


if __name__ == "__main__":
    if CLEAR:
        rmtree('out')

    makedirs('out', exist_ok=True)
    asyncio.run(main(NUM))
