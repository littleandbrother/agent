# 本轮边界
只做物理题目校准，不调用实验模型。最多800次完整瞬态、3小时、零API，输出250MB以内。
共享内核 ../sim.py；工具只能返回事实，不替方法推荐答案。四组百分比均为待测假设。
worker: feedback.py/active.py，structure.py/stopping.py，report.py 各自独立。
校准可以发现任务不成立，不能通过限制强基线或改掉服务要求来制造方法优势。
