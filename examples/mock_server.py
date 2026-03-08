import asyncio
import json
import argparse
from aiohttp import web


async def handle_delay(request):
    seconds = float(request.match_info.get("seconds", "1"))
    await asyncio.sleep(seconds)
    data = {
        "url": str(request.url),
        "args": dict(request.query),
        "origin": request.remote,
        "headers": dict(request.headers),
        "delay": seconds,
    }
    return web.json_response(data)


async def handle_status(request):
    code = int(request.match_info.get("code", "200"))
    return web.json_response({"status": code}, status=code)


async def handle_get(request):
    return web.json_response({
        "url": str(request.url),
        "args": dict(request.query),
        "origin": request.remote,
        "headers": dict(request.headers),
    })


async def handle_post(request):
    body = await request.text()
    return web.json_response({
        "url": str(request.url),
        "args": dict(request.query),
        "origin": request.remote,
        "data": body,
    })


async def handle_anything(request):
    body = await request.text()
    return web.json_response({
        "method": request.method,
        "url": str(request.url),
        "args": dict(request.query),
        "origin": request.remote,
        "data": body,
        "headers": dict(request.headers),
    })


def create_app():
    app = web.Application()
    app.router.add_get("/delay/{seconds}", handle_delay)
    app.router.add_get("/status/{code}", handle_status)
    app.router.add_get("/get", handle_get)
    app.router.add_post("/post", handle_post)
    app.router.add_route("*", "/anything", handle_anything)
    app.router.add_route("*", "/anything/{path:.*}", handle_anything)
    return app


def main():
    parser = argparse.ArgumentParser(description="Local mock HTTP server (replaces httpbin)")
    parser.add_argument("-p", "--port", type=int, default=9999, help="Port (default: 9999)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    args = parser.parse_args()

    app = create_app()
    print(f"\n  Mock server on http://{args.host}:{args.port}")
    print(f"  Routes: /delay/{{s}}, /status/{{code}}, /get, /post, /anything\n")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
