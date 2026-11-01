"""Start the Naver Shopping Scraper API.

    python server/run.py            # http://localhost:8000
    PORT=9000 python server/run.py  # another port

Then:  curl "http://localhost:8000/products/search?query=raspberry%20pi"
"""
import bottle
from cheroot import wsgi

import config
import listing_jobs
import routes  # noqa: F401  (mounts the routes on bottle's default app)


def main():
    app = bottle.default_app()
    listing_jobs.start_bridge()      # the browser extension connects here (/listings); optional
    print(f"Naver Shopping Scraper listening on http://localhost:{config.PORT}/")
    print(f"Try:  curl \"http://localhost:{config.PORT}/products/search?query=raspberry%20pi\"")
    server = wsgi.Server(("0.0.0.0", config.PORT), app, server_name="naver-shopping-scraper", numthreads=16)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
    finally:
        listing_jobs.stop_bridge()


if __name__ == "__main__":
    main()
