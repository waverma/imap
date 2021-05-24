import base64
import quopri
import ssl
from getpass import getpass

from socket import socket, AF_INET, SOCK_STREAM
from pyparsing import (nestedExpr, Literal, Word, alphanums,
                       quotedString, replaceWith, nums, removeQuotes, ParseResults)


def decode_header(text):
    b = text.split('?')
    if not ((len(b) == 5 or len(b) % 3 == 0) and b[0][-1] == '='):
        return text
    result = ''
    decode_method = None

    if b[2].upper() == 'B':
        decode_method = base64.b64decode
    if b[2].upper() == 'Q':
        decode_method = quopri.decodestring

    a = b[3::4]
    decoded_part = []
    for i in range(len(a)):
        decoded_part.append(decode_method(bytes(a[i], b[1])).decode(b[1]))
    commonly_part = []
    a = b[0::4]
    for i in range(len(a)):
        current_commonly_part = a[i]
        if i != 0:
            current_commonly_part = current_commonly_part[1:]
        if i != len(a) - 1:
            current_commonly_part = current_commonly_part[: -1]
        commonly_part.append(current_commonly_part)

    for i in range(len(decoded_part)):
        result += commonly_part[i]
        result += decoded_part[i]
    result += commonly_part[len(commonly_part) - 1]

    return result



def parse_mail(mail: list):
    if len(mail) == 0:
        return {}
    mail = mail[1:-2]
    keys = ['To', 'Subject', 'Date', "From"]
    i = 0
    cur_key = None
    result = dict()

    while len(mail) > i:
        a = mail[i].split(':')
        if a[0] in keys:
            cur_key = a[0]
            result[cur_key] = mail[i][len(cur_key) + 2:]
        elif cur_key is not None:
            if len(mail[i]) and (mail[i][0] == '\t' or mail[i][0] == ' '):
                result[cur_key] += mail[i][1:]
            else:
                cur_key = None
        i += 1

    b = result['Subject'].split('?')
    if b[0][-1] == '=':
        result['Subject'] = decode_header(result['Subject'])

    b = result['From'].split('?')
    if b[0][-1] == '=':
        result['From'] = decode_header(result['From'])

    if result['To'] == 'undisclosed-recipients:;':
        result['To'] = 'undisclosed recipients'

    return result


def parse_mails(response1, response2):
    current_message = []
    j = 0
    res = {}
    while len(response1) > j:
        line = ' '.join(response1[j])
        current_message.append(line)
        if line == ")":
            res[current_message[0].split(' ')[1]] = parse_mail(current_message)
            res[current_message[0].split(' ')[1]]["Size"] = current_message[0].split(' ')[-1][1:-1]
            current_message = []
        j += 1

    attach = {}
    for i in response2:

        NIL = Literal("NIL").setParseAction(replaceWith(None))
        integer = Word(nums).setParseAction(lambda t: int(t[0]))
        quotedString.setParseAction(removeQuotes)
        content = (NIL | integer | Word(alphanums))
        try :
            a = nestedExpr(content=content, ignoreExpr=quotedString).parseString(i[3])

            for part in a[0][1]:
                if type(part) is ParseResults:
                    size = -1
                    for part_info in part:

                        if type(part_info) is int and size == -1:
                            size = part_info
                        if type(part_info) is ParseResults and part_info[0] == 'attachment':
                            a = part_info[1][1]
                            if a[0:2] == '=?':
                                b = part_info[1][1].replace(' ', '').split('?')
                                if b[0][-1] == '=':
                                    a = decode_header(part_info[1][1].replace(' ', ''))
                            if i[1] not in attach:
                                attach[i[1]] = list()
                            attach[i[1]].append((a, str(size)))

        except Exception:
            pass

    for i in attach:
        res[i]['Attachments Count'] = str(len(attach[i]))
        k = 1
        for j in attach[i]:
            res[i][f'{k}'] = f'File name: {j[0]}, size: {j[1]}'
            k += 1

    for i in res:
        yield res[i]


def print_log(command, message):
    if command == "SERVER" or command == 'CLIENT':
        return
    sep = '\n'
    if type(message) is not str:
        t = list(filter(None, message.decode('utf-8').split(sep)))
    else:
        t = list(filter(None, message.split(sep)))
    for i in range(len(t)):
        if i == 0:
            t[i] = "\t" + t[i]
        else:
            t[i] = "\t\t" + t[i]

    print(f"{command}: {str.join(sep, t)}")


def get_addr(addr: str):
    s = addr.split(":")
    if len(s) == 2:
        return s[0], int(s[1])
    else:
        return s[0], 143


def parse_response(response: str):
    result = []
    j = 0
    cur = ''

    for i in range(len(response)):
        if response[i] == " " and j < 3:
            result.append(cur)
            j += 1
            cur = ''
        else:
            cur += response[i]

    result.append(cur)
    return result


class IMap:
    def __init__(self, user: str, use_ssl: bool, imap_server_address: str, mail_range: tuple = None):
        self.user = user
        self.use_ssl = use_ssl
        self.server = get_addr(imap_server_address)
        self.start, self.end = ('', '')
        if mail_range is None:
            self.start = self.end = -1
        else:
            if len(mail_range) == 1:
                self.start = self.end = mail_range[0]
            else:
                self.start, self.end = mail_range

        self.debug = True

        self.sock = None
        self.message_counter = 1


    def read_line(self) -> bytes:
        line = b''
        while True:
            s = self.sock.recv(1)
            if s == b'\r':
                if self.sock.recv(1) == b'\n':
                    break
            line += s

        return line

    def recv(self, queue_code: bytes) -> list:
        data = list()

        while True:
            line = self.read_line()
            data.append(line)
            if line[:len(queue_code)] == queue_code:
                break

        return data

    def send(self, message_id, text, recv=True):
        if self.debug:
            print_log("CLIENT", text)
        if type(text) is str:
            text = bytes(text, 'utf-8')
        self.sock.sendall(bytes(message_id, 'utf-8') + b' ' + text + b'\r\n')
        result = []
        if recv:
            data = self.recv(bytes(message_id, 'utf-8'))

            for line in data:
                l = line.decode('utf-8')
                if recv and self.debug:
                    print_log("SERVER", l)

                result.append(parse_response(line.decode('utf-8')))

        return result

    def run(self):
        try:
            self.sock = socket(AF_INET, SOCK_STREAM)
            if self.use_ssl:
                self.sock = ssl.wrap_socket(self.sock)
                self.server = (self.server[0], 993)
            self.sock.connect(self.server)
            m = self.sock.recv(1024)
            if self.debug: print_log("SERVER", m)
        except (OSError, ValueError):
            if self.debug: print_log('PROGRAM', 'invalid imap server or port')
            self.close()
        self.auth()
        self.send(self.get_message_id(), f'SELECT INBOX')
        self.fetch()
        self.send(self.get_message_id(), f'LOGOUT')

    def auth(self):
        a = self.get_message_id()

        print_log("PROGRAM", b"Your login is " + bytes(self.user, 'utf-8'))
        p = ''
        try:
            p = getpass(prompt='PROGRAM\t\tEnter password:')
        except KeyboardInterrupt:
            self.close()

        code = self.send(a, f'LOGIN {self.user} {p}')[0]
        if code[1] == 'BAD':
            if code[2] == '[PRIVACYREQUIRED]':
                print_log('PROGRAM', 'Error: ssl permission required')
                self.close()
        if code[1] == 'NO':
            if code[2] == '[AUTHENTICATIONFAILED]':
                print_log('PROGRAM', code[3])
                self.close()

    def fetch(self):
        if self.start == -1:
            response1 = self.send(self.get_message_id(), f'FETCH {self.start} body[]')
            response2 = self.send(self.get_message_id(), f'FETCH {self.start} BODYSTRUCTURE')
        else:
            response1 = self.send(self.get_message_id(), f'FETCH {self.start}:{self.end} body[]')
            response2 = self.send(self.get_message_id(), f'FETCH {self.start}:{self.end} BODYSTRUCTURE')
        d = parse_mails(response1[:-1], response2)
        for i in d:
            print_log("PROGRAM", '-'*100)
            for j in i:
                print_log("PROGRAM", f'{j}: {i[j]}')
        print_log("PROGRAM", '-'*100)

    def get_message_id(self):
        self.message_counter += 1
        return f'A0{self.message_counter - 1}'

    def close(self):
        self.sock.close()
        quit()
