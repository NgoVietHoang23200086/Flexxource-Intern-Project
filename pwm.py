from gpiozero import PWMLED
from time import sleep

# Khởi tạo GPIO BCM 4 với tần số 1000Hz (1kHz)
pwm = PWMLED(26, frequency=1000)

try:
    while True:
        print("Duty Cycle: 100%")
        pwm.value = 1.0
        sleep(5)

except KeyboardInterrupt:
    pwm.off()
    sleep(10)
    print("Dừng chương trình.")
