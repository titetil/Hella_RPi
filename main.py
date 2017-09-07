print('starting program')
import os
import time
import read_PWM
import queue
from threading import Thread

try:
    os.system("sudo pigpiod")
except Exception as e:
    print('pigiod error:')
    print(e)
try:
    os.system("sudo /sbin/ip link set can0 up type can bitrate 500000")
except Exception as e:
    print('CAN setup error:')
    print(e)

import pigpio
import can

bus = can.interface.Bus(channel='can0', bustype='socketcan_native')
current_milli_time = lambda: int(round(time.time() * 1000)) #time is in milliseconds
current_time = current_milli_time()
prev_time_1 = current_time
prev_time_2 = current_time

PWM_GPIO = 23
pi = pigpio.pi()
p = read_PWM.reader(pi, PWM_GPIO)
prev_duty = 0
prev_counter = 0
prev_tick = 0

msg_1 = 0
msg_2 = 0
multiplier_1 = 3040238857
multiplier_2 = 4126034881
addend_1 = 2094854071
addend_2 = 3555108353
sec_ecu_key_37 = 3360791710
key_data = [0x6, 0x27, 0x38, 0x0, 0x0, 0x0, 0x0, 0x55]
response_1 = []
response_2 = []

def can_rx_task():	# Receive thread
    while True:
        try:
            message = bus.recv()
            if message.arbitration_id == 0x7EB:
                q.put(message)			# Put message into queue
        except Exception as e:
            print('CAN Rx error:')
            print(e)
            time.sleep(0.01)

q = queue.Queue()
rx = Thread(target = can_rx_task)
rx.start()

def flush_queue():
    with q.mutex:
        q.queue.clear()

def security_access():
    # Initialization message to controller
    print('security access...')

    try:
        msg=can.Message(arbitration_id=0x7E3, data=[0x2, 0x10, 0x3, 0x55, 0x55, 0x55, 0x55, 0x55], extended_id=False)
        bus.send(msg)
        print(msg)
    except:
        print('CAN error')
    print('continue')

        # Check for initialization response
    resp_flag = False
    for i in range(25):
        print('in loop')
        try:
            response_1 = q.get_nowait()
            print('response_1')
            print(response_1)
            if response_1.arbitration_id == 0x7EB and response_1.data[1] == 0x50:
                resp_flag = True
                flush_queue()
                break
        except Exception as e:
            print('response_1 queue error:')
            print(e)
            time.sleep(0.01)

    if resp_flag:
        # First security request message
        msg=can.Message(arbitration_id=0x7E3, data=[0x2, 0x27, 0x37, 0x0, 0x0, 0x0, 0x0, 0x0], extended_id=False)
        bus.send(msg)
        print(msg)

        # Check for first security response
        resp_flag = False
        for i in range(25):
            try:
                response_1 = q.get_nowait()
                print('response_1-2')
                print(response_1)
                time.sleep(0.001)
                if response_1.arbitration_id == 0x7EB and response_1.data[2] == 0x67:
                    resp_flag = True
                    flush_queue()
                    break
            except Exception as e:
                print('response_1-2 queue error:')
                print(e)
                time.sleep(0.01)

    else:
        print('Security Access FAILED_1')
        return False

    if resp_flag:
        # Second security request message
        msg=can.Message(arbitration_id=0x7E3, data=[0x30, 0x8, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0], extended_id=False)
        bus.send(msg)
        print(msg)

        # Check for second security response
        resp_flag = False
        for i in range(25):
            try:
                response_2 = q.get_nowait()
                print('response_2')
                print(response_2)
                time.sleep(0.001)
                if response_2.arbitration_id == 0x7EB and response_2.data[0] == 0x21:
                    resp_flag = True
                    flush_queue()
                    break
            except Exception as e:
                print('response_2 queue error:')
                print(e)
                time.sleep(0.01)

    else:
        print('Security Access FAILED_2')
        return False

    if resp_flag:
        msg_1 = 0
        msg_2 = 0
        for i in range(4, 8):
            msg_1 = msg_1 | response_1.data[i]
            if i != 7:
                msg_1 = msg_1 << 8

        for i in range(1, 5):
            msg_2 = msg_2 | response_2.data[i]
            if i != 4:
                msg_2 = msg_2 << 8

        calculated_seed_x = (((msg_1 * multiplier_1) & 0xffffffff) + addend_1) & 0xffffffff
        calculated_seed_y = (((msg_2 * multiplier_2) & 0xffffffff) + addend_2) & 0xffffffff
        security_key = (calculated_seed_x ^ calculated_seed_y ^ sec_ecu_key_37)
        # Assemble the security key message
        for i in range(4):
            key_data[6 - i] = security_key & 0xFF
            security_key = security_key >> 8

        msg=can.Message(arbitration_id=0x7E3, data=key_data, extended_id=False)
        bus.send(msg)
        print(msg)

        print('Security Access Complete')
        return True

    else:
        print('Security Access FAILED_3')
        return False

def release_controller():
    print('release controller')
    msg = can.Message(arbitration_id=0x7E3, data=[0x04, 0x2F, 0xDB, 0x06, 0x00, 0x00, 0x00, 0x00], extended_id=False)
    bus.send(msg)
    print(msg)

def send_CAN(msg):
    try:
        print(msg)
        bus.send(can.Message(arbitration_id=0x7e3, data=msg, extended_id=False))
    except Exception as e:
        print('CAN message send error:')
        print(e)
        security_access()

while True:
    #read duty cycle from RIO
    try:
        tick = p.tick or 0
        if tick == prev_tick:
            input_state = p.input_state()
            if input_state == 0:
                duty = 0
            else:
                duty = 100
        else:
            duty = round(p.duty_cycle())
            if duty > 100:
                duty = 0
    except Exception as e:
        duty = 0
        print('duty cycle read error')
        print(e)
    finally:
        prev_tick = tick

    #set zero_command flag
    if duty == 0 and prev_duty != 0:
        zero_command = True
    else:
        zero_command = False

    #need to repeat "0" command a few times to shut pump off
    if zero_command:
        zero_counter = 5
    else:
        zero_counter = prev_counter
    prev_counter = zero_counter - 1

    if zero_counter == 0:
        release_controller()
        print('done repeating zero')

    current_time = current_milli_time()

    #main CAN message case
    if duty !=0 and prev_duty == 0: #and not secure_conn:  # Command was zero, now non-zero, so send controller initilization messages.
        sec_success = False
        while not sec_success:
            sec_success = security_access()
            flush_queue()
            time.sleep(0.01)

    if duty != 0 or zero_command or zero_counter > 0:  #Non-zero command, so send CAN message.
        if (current_time - prev_time_1) > 1000:  #This message needs to be sent every second.
            msg_1 = [0x02, 0x3E, 0x00, 0x55, 0x55, 0x55, 0x55, 0x55]
            send_CAN(msg_1)
            prev_time_1 = current_time

        if (current_time - prev_time_2) > 100:  #Send the PWM command message every 100ms.
            try:
                pwm_cmd = duty  #transfer from RIO pwm command to CAN pwm command should be 1:1
                msg_2 = [0x05, 0x2F, 0xDB, 0x06, 0x03, pwm_cmd, 0x55, 0x55]
                send_CAN(msg_2)
                prev_time_2 = current_time
            except Exception as e:
                print(e)

        time.sleep(0.01) #Wait at least 10ms, or else RIO CPU will max out.
    else:
        time.sleep(0.2)  #no CAN message to be sent, so delay for 200ms

    flush_queue()
    prev_duty = duty
