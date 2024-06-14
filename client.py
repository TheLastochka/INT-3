import socket
import json
import sys
import signal
import select

CONFIG_FILENAME = 'client.config.json'

COMMANDS = ''
FORMAT = ''
SOCKET = None

def send_and_receive(ADDR, request):
    global SOCKET
    SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SOCKET.setblocking(False)
    try:
        SOCKET.connect_ex(ADDR)
        print('Waiting for server... (period 3s)')
        while True:
            ready = select.select([], [SOCKET], [], 3)
            if ready[1]:
                SOCKET.send(request)
                break
        while True:
            ready = select.select([SOCKET], [], [], 3)
            if ready[0]:
                response = SOCKET.recv(1024)
                return response, None
    except Exception as e:
        return None, f'Socket error: {e}'
    finally:
        SOCKET.close()

def load_commands_and_format(ADDR):
    global COMMANDS, FORMAT
    response, error = send_and_receive(ADDR, b'commands')
    if error:
        print('Failed to load commands and format:', error)
        sys.exit(1)
    
    data = json.loads(response.decode('utf-8'))
    if 'error' in data:
        print('Error:', data['error'])
        sys.exit(1)
    
    COMMANDS = data['data']['commands']
    FORMAT = data['data']['format']

def print_help():
    print('Usage: python client.py <json request filename>')
    print('Request format:')
    print(FORMAT)
    print('Commands:')
    print(COMMANDS)

def read_config_ADDR():
    config = None
    with open(CONFIG_FILENAME) as f:
        config = json.load(f)
    if config is None:
        return (None, f'Failed to read config from file {CONFIG_FILENAME}')
    HOST = config['HOST']
    PORT = int(config['PORT'])
    if HOST is None or PORT is None:
        return (None, 'Invalid config: HOST or PORT not found')
    return ((HOST, PORT), None)

def main():
    ADDR, error = read_config_ADDR()
    if ADDR is None:
        print(error)
        return
    print('Address:', ADDR)
    
    if len(sys.argv) != 2:
        load_commands_and_format(ADDR)
        print_help()
        return
    filename = sys.argv[1]

    request = None
    with open(filename) as f:
        request = json.load(f)
    if request is None:
        print('Failed to read request from file')
        return
    request = json.dumps(request).encode('utf-8')

    response, error = send_and_receive(ADDR, request)
    if error:
        print('Failed to send request:', error)
        return

    print('=== Response ===')
    data = json.loads(response.decode('utf-8'))
    if 'error' in data:
        print('Error')
        print(data['error'])
    else:
        print('Success')
        print(data['data'])
    
def handle_sigint(signal, frame):
    print('Client stopping...')
    if SOCKET is not None:
        SOCKET.close()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, handle_sigint)
    main()
