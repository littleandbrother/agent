# 当前 typed CLI 入口
工程身份：project info；文档：project doc；原理图：sch read；PCB：pcb list / pcb dump / pcb drc。
器件：lib search / lib resolve / lib device / lib footprint。指定当前库和实际 identity，再调用 sch replace / sch add。
保存：sch save / pcb save；按当前连接器支持的 reload、read/dump 核对持久化。
同步：pcb import-changes 使用 --no-sync-attrs，输入为当前原理图和对应 PCB。
flags 取已缓存 argv=[域,动作,"--help"]。旧回执 argv 可通过 bf_workspace json 读取。
完整参考先用 bf_skill catalog/resource 核对 vendor/easyeda-typed/references 路径，再按操作读取。
原写动作保留操作身份；超时后查原回执和读回。
上游：https://github.com/zhoushoujianwork/easyeda-agent
