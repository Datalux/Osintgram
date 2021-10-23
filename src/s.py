from Command import CommandParent

class Test(CommandParent):
    def execute(self):
        return "test"

p = CommandParent()
t = Test()

print(p.execute())            
print(t.execute())            