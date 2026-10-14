# 参数与几何
参数、几何检查、导出分开。参数一次返回名字、值、单位、来源行和 SHA；几何一次返回尺寸、实体、孔位、干涉和 STEP 引用。变化给出前后值及影响接口。
读取已有 CadQuery/STEP 作业；输入与条件未变时引用原作业。修改后由原执行器导出、读回，核对 PCB 到 CAD 变换和孔位。
参考：https://github.com/CadQuery/cadquery-contrib/tree/master/mcp-server
# 接口记录

bf-interface-bindings-v1 的 facts.source 使用候选文件 path、sha256 及精确选择器：JSON 用 json_pointer（如 /checks/2/pcb_mm/0）；CAD Python 字面参数用 symbol（如 P.pcb_l）或工具返回的 fact_id（如 cad.P.pcb_l）；Nordic 已提取时序用 fact_id（如 ble.advertising_ms）。程序读取来源值再比较，单位由实际定义确认。line 可补充定位。

