
# Bash Emulator - Stage 5 (Final)

## Overview
This is the final stage of a Bash-like console emulator written in Python.  
It supports a virtual file system (VFS) stored as a ZIP archive and performs all operations in memory.

## Features
- Interactive CLI with realistic prompt: `user@host:/path$`
- Commands implemented:
  - `ls` – List directory contents with permissions
  - `cd` – Change current directory
  - `tree` – Show directory hierarchy
  - `cal` – Show monthly calendar
  - `mkdir` – Create a new directory (in-memory only)
  - `chmod` – Change permissions of a file or directory (in-memory only)
  - `help` – Show list of commands with descriptions
  - `exit` – Exit emulator

## Usage
```bash
python3 emulator_stage5.py --vfs sample_vfs.zip --startup startup_stage5.sh
```

## Notes
- All file and directory operations happen in memory. No actual filesystem changes occur.
- The VFS is loaded from a ZIP archive.
- The `startup_stage5.sh` file demonstrates all implemented commands and error handling.
