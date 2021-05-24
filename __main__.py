import argparse

from imap import IMap

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssl", action='store_true', help="разрешить использование ssl, если сервер поддерживает (по умолчанию не использовать)")
    parser.add_argument("-s", "--server", type=str, required=True, help="адрес (или доменное имя) IMAP-сервера в формате адрес[:порт] (порт по умолчанию 143).")
    parser.add_argument("-u", "--user", type=str, help="имя пользователя, пароль спросить после запуска и не отображать на экране.")
    parser.add_argument('-n', nargs='*', default=['-1'], help='диапазон писем, по умолчанию все.')
    args = parser.parse_args()
    IMap(args.user, args.ssl, args.server, args.n).run()