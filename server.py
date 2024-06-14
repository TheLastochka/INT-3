import socket
import json
import sys
import os
import threading
import signal
import select

CONFIG_FILENAME = 'server.config.json'

COMMANDS = [
    {
        'name': 'CheckLocalFile',
        'description': 'Check a local file for malware',
        'params': {
            'file_path': 'string, path to file to check',
            'signature': 'string, signature bytes of malware in hex format'
        }
    },
    {
        'name': 'QuarantineLocalFile',
        'description': 'Quarantine a local file',
        'params': {
            'file_path': 'string, path to file to quarantine'
        }
    }
]

FORMAT = '''{
    "command": COMMAND,
    "params": {
        PARAM1: VALUE1,
        PARAM2: VALUE2,
        ...
    }
}
'''

THREADS_NUM = None
PORT = None
QUARANTINE_DIR = ''

def load_config():
    global THREADS_NUM, PORT, QUARANTINE_DIR
    config = None
    with open(CONFIG_FILENAME, 'r') as f:
        config = json.load(f)
    if config is None:
        print('Failed to load config')
        sys.exit(1)
    
    THREADS_NUM = int(config['THREADS_NUM'])
    PORT = int(config['PORT'])
    QUARANTINE_DIR = config['QUARANTINE_DIR']

def commands_to_str(commands):
    commands_str = ''
    for command in commands:
        commands_str += f'\t{command["name"]}: {command["description"]}\n'
        commands_str += '\t\tParams:\n'
        for param, type in command['params'].items():
            commands_str += f'\t\t\t{param}: {type}\n'
    return commands_str

def parse_request(request):
    command = request.get('command')
    if not command:
        return (None, 'Command not found in request')
    command_names = [cmd['name'] for cmd in COMMANDS]
    if command not in command_names:
        return (None, f'Invalid command: {command}')
    
    params = request.get('params')
    if not params:
        return (None, 'Params not found in request')
    
    command_def = COMMANDS[command_names.index(command)]
    for param in params:
        if param not in command_def['params']:
            return (None, f'Invalid param: {param}')
    
    return ((command, params), None)

def handle_client(conn):
    try:
        print(f'New connection from {conn.getpeername()}')
        data = conn.recv(2048)

        if data == b'commands':
            print(f'Sending commands to {conn.getpeername()}')
            conn.send(json.dumps({'data': {'commands': commands_to_str(COMMANDS), 'format': FORMAT}}).encode('utf-8'))
        else:
            data = data.decode('utf-8')
            data = json.loads(data)
            (command, params), err = parse_request(data)
            if err is not None:
                conn.send(json.dumps({'error': err}).encode('utf-8'))
            else:
                data_to_send, err = handle_command(command, params)
                if err is not None:
                    conn.send(json.dumps({'error': err}).encode('utf-8'))
                else:
                    conn.send(json.dumps({'data': data_to_send}).encode('utf-8'))

    except Exception as e:
        print('Failed to handle client request:', e)
        try:
            conn.send(json.dumps({'error': f'Failed to handle request: {e}'}).encode('utf-8'))
        except:
            print(f'Connection from {conn.getpeername()} closed')
    finally:
        conn.close()

def handle_command(command, params):
    if command == 'CheckLocalFile':
        file_path = params['file_path']
        signature = params['signature']
        print(f'Checking file {file_path} for malware with signature {signature}')
        offsets, err = checkLocalFile(file_path, signature)
        return (offsets, err)
    elif command == 'QuarantineLocalFile':
        file_path = params['file_path']
        print(f'Quarantining file {file_path}')
        data, err = quarantineLocalFile(file_path)
        return (data, err)
    else:
        print(f'Unknown command {command}')
        return (None, f'Unknown command {command}')

def checkLocalFile(file_path, signature):
    if not os.path.exists(file_path):
        return (None, f'File {file_path} not found')

    with open(file_path, 'rb') as f:
        data = f.read()
        signature = bytes.fromhex(signature)
        offsets = [i for i in range(len(data)) if data[i:i+len(signature)] == signature]
        print(f'Found {len(offsets)} occurrences of malware in file {file_path}')
        return (offsets, None)
    
def quarantineLocalFile(file_path):
    if not os.path.exists(file_path):
        return None, f'File {file_path} not found'
    
    if not os.path.exists(QUARANTINE_DIR):
        os.makedirs(QUARANTINE_DIR)
    
    file_name = os.path.basename(file_path)
    new_file_path = os.path.join(QUARANTINE_DIR, file_name)
    os.rename(file_path, new_file_path)
    print(f'File {file_path} quarantined to {new_file_path}')
    return 'File successfully quarantined', None

SOCKET = None
CURRENT_THREADS = []
RUNNING = True

def handle_sigint(signal, frame):
    global RUNNING
    print('Server stopping...')
    RUNNING = False
    if SOCKET is not None:
        SOCKET.close()
    for t in CURRENT_THREADS:
        t.join()
    sys.exit(0)

def main():
    global SOCKET, CURRENT_THREADS, RUNNING
    load_config()

    SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    SOCKET.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    SOCKET.bind(('localhost', PORT))
    SOCKET.listen(5)
    SOCKET.setblocking(False)
    print(f'Server started on port {PORT}')

    CURRENT_THREADS = []
    signal.signal(signal.SIGINT, handle_sigint)

    while RUNNING:
        try:
            ready_to_read, _, _ = select.select([SOCKET], [], [], 1)
            if ready_to_read:
                conn, addr = SOCKET.accept()
                CURRENT_THREADS = [t for t in CURRENT_THREADS if t.is_alive()]
                if len(CURRENT_THREADS) >= THREADS_NUM:
                    print(f'Server is busy. Rejecting connection from {addr}')
                    conn.send(json.dumps({'error': 'Server is busy'}).encode('utf-8'))
                    conn.close()
                    continue
                t = threading.Thread(target=handle_client, args=(conn,))
                CURRENT_THREADS.append(t)
                t.start()
        except Exception as e:
            print(f'Error accepting connection: {e}')

if __name__ == '__main__':
    main()
