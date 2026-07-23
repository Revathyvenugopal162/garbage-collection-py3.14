import os
import time

counter = 0

print(f"PID={os.getpid()}")

while True:
    counter += 1
    print(f"counter={counter}")
    time.sleep(5)