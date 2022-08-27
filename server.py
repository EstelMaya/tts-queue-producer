from os import getuid, getenv
from aiohttp import web, ClientSession
from aio_pika import connect_robust, Message
from uuid import uuid4
from asyncio import get_event_loop
from functools import partial
from json import dumps
import ssl

RABBIT_HOST = getenv('RABBIT_HOST', 'rabbitmq.example.com')
RABBIT_USER = getenv('RABBIT_USER', 'admin')
RABBIT_PASS = getenv('RABBIT_PASS', '')
TTS_URL = getenv('TTS_URL', '')
RABBIT_PORT = int(getenv('RABBIT_PORT', 5672))

CORS_ENABLED = bool(int(getenv('CORS_ENABLED', 0)))
HTTPS_ENABLED = bool(int(getenv('HTTPS_ENABLED', 0)))

QUEUE = 'tts_queue'
QUEUE_REALTIME = 'tts_realtime'
CLIENT_MAX_SIZE_BYTES = int(getenv('CLIENT_MAX_SIZE_BYTES', 10240))
CLIENT_MAX_CHARS = int(getenv('CLIENT_MAX_CHARS', 10000))
# Queing time
RABBIT_EXPIRATION_SEC = 600


async def on_realtime(future, res, msg):
    if (c := msg.body):
        await res.write(c)
    else:
        future.set_result(True)


async def produce(request):
    print('Message processing started')
    callback_queue = None
    consumer_tag = None
    channel = None
    try:
        channel = await connection.channel()

        msg = await request.json()
        headers = {}

        if CORS_ENABLED:
            headers['Access-Control-Allow-Origin'] = '*'

        total_chars = 0
        for obj in msg['data']:
            if obj['type'] == 'text':
                total_chars += sum(len(d['text']) for d in obj['data'])

        if total_chars > CLIENT_MAX_CHARS:
            return web.Response(status=413, content_type='text/plain', headers=headers)

        res = web.StreamResponse(headers=headers)
        format = msg['format']
        is_realtime = format == 'pcm'
        future = loop.create_future()
        callback_queue = await channel.declare_queue(exclusive=True)

        routing_key = QUEUE_REALTIME if is_realtime else QUEUE

        await channel.default_exchange.publish(
            Message(
                dumps(msg).encode(),
                correlation_id=uuid4().hex,
                reply_to=callback_queue.name,
                expiration=RABBIT_EXPIRATION_SEC
            ), routing_key=routing_key)

        res.content_type = 'audio/' + \
            format if format in {'mp3', 'ogg'} else 'audio/wav'

        if is_realtime:
            res.enable_chunked_encoding()
            await res.prepare(request)
            consumer_tag = await callback_queue.consume(partial(on_realtime, future, res))
        else:
            consumer_tag = await callback_queue.consume(lambda msg: future.set_result(msg.body))

        response = await future
        if not is_realtime:
            await res.prepare(request)
            await res.write(response)
        return res
    finally:
        print('Finished')
        if callback_queue and consumer_tag:
            await callback_queue.cancel(consumer_tag)
            await callback_queue.delete()
            await channel.close()


async def voices_redirect(request):
    path = request.path
    async with ClientSession() as session:
        async with session.get(TTS_URL+path) as r:
            voices = (await r.text()).split('\n')[:-1]

    return web.json_response(voices)


async def whoami(_):
    text = "AMAI TTS producer ver. 0.0.24\nImplemented by: k@amai.io\nAdapted by: p.dondukov@amai.io"

    headers = {}
    if CORS_ENABLED:
        headers['Access-Control-Allow-Origin'] = '*'

    return web.Response(text=text, content_type='text/plain', headers=headers)


async def getvars(_):
    variables = {
        "CLIENT_MAX_SIZE_BYTES": CLIENT_MAX_SIZE_BYTES,
        "CLIENT_MAX_CHARS": CLIENT_MAX_CHARS
    }

    headers = {}
    if CORS_ENABLED:
        headers['Access-Control-Allow-Origin'] = '*'

    return web.json_response(variables, headers=headers)


if __name__ == "__main__":
    loop = get_event_loop()
    connection = loop.run_until_complete(connect_robust(
        login=RABBIT_USER, password=RABBIT_PASS, host=RABBIT_HOST, port=RABBIT_PORT))

    app = web.Application(client_max_size=CLIENT_MAX_SIZE_BYTES)
    app.add_routes([
        web.post('/synth', produce),
        web.get('/whoami', whoami),
        web.get('/getvars', getvars),
        web.get('/voices', voices_redirect),
        web.get('/all-voices', voices_redirect),
        web.get('/', lambda _: web.Response(content_type='application/json'))
    ])

    if HTTPS_ENABLED:
        port = 443 if getuid() == 0 else 8443
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain('tls.crt', 'tls.key')
    else:
        port = 80 if getuid() == 0 else 8080
        ssl_context = None

    web.run_app(app, access_log=None, port=port,
                loop=loop, ssl_context=ssl_context)
