
# Startup script for Stage 5 emulator testing
echo "=== Testing ls and tree ==="
ls
tree
echo "=== Testing mkdir ==="
mkdir newdir
mkdir newdir/subdir
ls
tree
echo "=== Testing chmod ==="
chmod 700 newdir
chmod 644 hello.txt
ls
echo "=== Testing cal ==="
cal
echo "=== Testing cd and ls ==="
cd newdir
pwd
ls
cd ..
echo "=== Testing help ==="
help
echo "=== Testing error handling ==="
chmod 9999 nofile
mkdir existing
exit 0
