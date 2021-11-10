import yaml
from src import utils as utils

class OsintgramStatus:

    __default_commands_ = [
        'help',
        'exit',
        'set',
        'options'
    ]

    def __init__(self):
        self.command_mode = False
        self.setted_subcommand = False
        self.command = ""
        self.subcommand = ""
        self.commands = []
        self.output_config = []
        self.target = None

    def get_command(self):
        return self.command

    def set_command(self, command):
        self.command_mode = True
        self.command = command
        stream = open(self.get_path(), 'r')
        setup = yaml.safe_load(stream)
        self.commands = setup['commands']
        if self.commands is not None:
            self.commands.extend(self.__default_commands_)

    def get_target(self):
        return self.target

    def set_target(self, target):
        self.target = target      

    def get_subcommand(self):
        return self.subcommand

    def set_subcommand(self, command):
        self.subcommand = command
        self.setted_subcommand = True

    def is_command_mode(self):
        return self.command_mode

    def is_subcommand(self):
        return self.setted_subcommand
    
    def get_commands(self):
        return self.commands

    def set_commands(self, commands):
        self.commands = commands

    def set_output_config(self, output_config):
        self.output_config = output_config

    def get_path(self):
        return "src/commands/" + self.command + "/config.yaml"
    
    def get_module(self):
        return "src.commands." + self.command + ".run"

    def release(self):
        self.command = ""
        self.subcommand = ""
        self.command_mode = False
        self.setted_subcommand = False
        stream = open("src/setup.yaml", 'r')
        setup = yaml.safe_load(stream)
        self.commands = setup['commands']

    def print_output(self, data, table_header = [], table_contents = [], no_table = False):
        for output in self.output_config:
            if output == 'table':
                if not no_table:
                    utils.print_in_table(data, table_header, table_contents)
            elif output == "json":
                utils.print_in_json(data, self)   
            elif output == "csv":
                if not no_table:
                    utils.print_in_csv(data, table_contents, self)
