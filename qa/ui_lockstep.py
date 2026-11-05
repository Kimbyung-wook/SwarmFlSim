"""UI 확인용: 실행 중인 recovery_stack(48281)을 Reset 뒤 lockstep 2배속으로 다시 시작한다."""
import sys, time
sys.path.insert(0, "qa")
import harness as h
ob = h.Observer(["tcp/127.0.0.1:48281"])
time.sleep(2)
ob.reset()
ob.wait(lambda: ob.status.state == ob.m[0].SIM_RUN_STATE_LOADED, 20)
time.sleep(2)
ob.start("lockstep", 2.0)
print("lockstep started", ob.wait(lambda: (ob.last_frame or 0) > 100, 30), ob.last_frame)
ob.close()
