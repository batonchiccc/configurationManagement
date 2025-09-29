import os
import socket
import sys
import getpass

def get_prompt():
    username = getpass.getuser()
    hostname = socket.gethostname()
    cwd = os.getcwd()
    home = os.path.expanduser("~")

    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    
    return f"{username}@{hostname}:{cwd}$ "

def parse_command(input):
    parts = input.strip().split()

    if not parts:
        return None, []
    return parts[0], parts[1:]
    
def process_command(cmd, args):
    #add switch case later switch case 
    match cmd:
        case "exit":
             if args: 
                return f"command error: exit - too many arguments \n"
             else:
                sys.exit() 
                
        case "ls":
            return f"called {cmd} with arguments: {args}"
        case "cd":
            return f"called {cmd} with arguments: {args}"
    return f"command '{cmd}' not found"

def main():
    print("REPL prototype")

    while True:
        try:
            prompt = get_prompt()
            user_input = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()  # новая строка при Ctrl+D / Ctrl+C
            break

        cmd, args = parse_command(user_input)

        if cmd is None:
            continue  # пустой ввод
        else:
            print(process_command(cmd, args))
        
if __name__ == "__main__":
    main()