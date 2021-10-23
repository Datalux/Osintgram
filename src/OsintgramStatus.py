import yaml

class OsintgramStatus:

    def __init__(self):
        self.command_mode = False
        self.setted_subcommand = False
        self.command = ""
        self.subcommand = ""
        self.commands = []

    def get_command(self):
        return self.command

    def set_command(self, command):
        self.command_mode = True
        self.command = command
        stream = open(self.get_path(), 'r')
        setup = yaml.safe_load(stream)
        self.commands = setup['commands']

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

    def get_path(self):
        return "src/commands/" + self.command + "/config.yaml"
    
    def get_module(self):
        return "src.commands." + self.command + ".run"

