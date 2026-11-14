"""Safe local launcher for the CityLab Diagnostics web application on port 8001."""
import os
import socket
import sys
from pathlib import Path
import uvicorn


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main() -> int:
    root = Path(__file__).resolve().parent
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    host = os.getenv('HOST', '127.0.0.1').strip() or '127.0.0.1'
    port = int(os.getenv('PORT', '8001'))

    if _port_in_use(host, port):
        print(
            f'ERROR: {host}:{port} is already occupied by another process. '
            'Stop only your own CityLab server or choose another PORT before retrying.',
            file=sys.stderr,
        )
        return 1

    print(f'Starting CityLab Diagnostics web application at http://{host}:{port}')
    uvicorn.run('backend.app.main:app', host=host, port=port)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
