import yaml
from src import utils
from src import OsintgramStatus
import sys
import signal
import argparse
from src import printcolors as pc
import readline
from src.Osintgram import Osintgram



def signal_handler(sig, frame):
    pc.printout("\nGoodbye!\n", pc.RED)
    sys.exit(0)


def completer(text, state):
    options = [i for i in status.get_commands() if i.startswith(text)]
    if state < len(options):
        return options[state]
    else:
        return None

def _quit():
    pc.printout("Goodbye!\n", pc.RED)
    sys.exit(0)   



parser = argparse.ArgumentParser(description='Osintgram is a OSINT tool on Instagram. It offers an interactive shell '
                                             'to perform analysis on Instagram account of any users by its nickname ')
parser.add_argument('id', type=str,  # var = id
                    help='username')
parser.add_argument('-C','--cookies', help='clear\'s previous cookies', action="store_true")
parser.add_argument('-j', '--json', help='save commands output as JSON file', action='store_true')
parser.add_argument('-f', '--file', help='save output in a file', action='store_true')
parser.add_argument('-c', '--command', help='run in single command mode & execute provided command', action='store')
parser.add_argument('-o', '--output', help='where to store photos', action='store')

args = parser.parse_args()    


signal.signal(signal.SIGINT, signal_handler)
# if is_windows:
#     pyreadline.Readline().parse_and_bind("tab: complete")
#     pyreadline.Readline().set_completer(completer)
# else:
#     gnureadline.parse_and_bind("tab: complete")
#     gnureadline.set_completer(completer) 

stream = open("src/setup.yaml", 'r')
setup = yaml.safe_load(stream)

parser = argparse.ArgumentParser(description='Osintgram is a OSINT tool on Instagram. It offers an interactive shell '
                                             'to perform analysis on Instagram account of any users by its nickname ')
parser.add_argument('id', type=str,  # var = id
                    help='username')
parser.add_argument('-C','--cookies', help='clear\'s previous cookies', action="store_true")
parser.add_argument('-j', '--json', help='save commands output as JSON file', action='store_true')
parser.add_argument('-f', '--file', help='save output in a file', action='store_true')
parser.add_argument('-c', '--command', help='run in single command mode & execute provided command', action='store')
parser.add_argument('-o', '--output', help='where to store photos', action='store')

args = parser.parse_args() 

if not args.command:
    utils.printlogo(setup['version'], setup['author'])

status = OsintgramStatus.OsintgramStatus()

api = Osintgram(args.id, args.file, args.json, args.command, args.output, args.cookies)

command = None

status.set_commands(setup['commands'])
status.set_output_config(setup['output_config'])
status.set_target(api.get_target())


while True:
    signal.signal(signal.SIGINT, signal_handler)
    
    completer = utils.Completer(status.get_commands())
    readline.set_completer_delims(' \t\n;')
    readline.set_completer(completer.complete)
    readline.parse_and_bind('tab: complete')

    if(status.is_command_mode()):
        pc.printout(status.get_command() + '> ', pc.GREEN)
    else:
        pc.printout("Run a command: ", pc.YELLOW)
    cmd = input()
    
    if cmd in status.get_commands():
        _cmd = cmd

        if status.is_command_mode():
            status.set_subcommand(cmd)
        else:
            status.set_command(cmd)
    else:
        _cmd = None

    if _cmd:
        __import__(status.get_module())
        mymodule = sys.modules[status.get_module()]
        if status.is_subcommand():
            command.__getattribute__(_cmd)()
        else:
            command = mymodule.Command(status, api)
            
    elif _cmd == "":
        print("")
    else:
        pc.printout("Unknown command\n", pc.RED)

    if args.command:
        break


