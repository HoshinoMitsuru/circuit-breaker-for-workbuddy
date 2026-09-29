"""CLI 入口：check / watch / discover / config / status。

运行：python -m circuit_breaker.cli <subcommand>
"""

import argparse
import glob
import json
import os
import sys

from .config import Config
from . import discover as discover_mod
from .monitor import check_once, run


def _cmd_config(args, config: Config):
    if args.show:
        print(json.dumps(config.data, ensure_ascii=False, indent=2))
        print(f"\n配置文件：{config.path}")
        return
    if args.set_workspace_budget is not None:
        config.set_workspace_budget(args.workspace, args.set_workspace_budget)
        print(f"已设置 工作空间[{args.workspace}] 预算={args.set_workspace_budget}")
    if args.set_default_budget is not None:
        config.data["default_budget"] = args.set_default_budget
        config.save()
        n = args.set_default_budget
        tag = "（0=无上限，不熔断）" if n <= 0 else ""
        print(f"已设置 默认预算(default_budget)={n}{tag}")
    if args.set_task_budget is not None:
        config.set_task_budget(args.workspace, args.task, args.set_task_budget)
        print(f"已设置 工作空间[{args.workspace}] 任务[{args.task}] 预算={args.set_task_budget}")
    if args.set_reader_field:
        config.data["reader"]["field"] = args.set_reader_field
        config.save()
        print(f"reader.field={args.set_reader_field}（remaining=界面显示剩余；used=界面显示已用）")
    if args.set_keyword:
        config.data["reader"]["keyword"] = args.set_keyword
        config.save()
        print(f"reader.keyword={args.set_keyword}")
    if args.set_thresholds:
        w, t = args.set_thresholds
        config.data["thresholds"]["warn"] = w
        config.data["thresholds"]["trip"] = t
        config.save()
        print(f"thresholds warn={w} trip={t}")
    if not any([args.show, args.set_workspace_budget is not None,
                args.set_task_budget is not None, args.set_reader_field,
                args.set_keyword, args.set_thresholds]):
        print(f"配置文件：{config.path}")
        print("用法：circuit-breaker config --show | --set-workspace-budget <ws> <n> | "
              "--set-task-budget <ws> <task> <n> | --set-reader-field remaining|used | "
              "--set-keyword <词> | --set-thresholds <warn> <trip>")


def _cmd_check(args, config: Config):
    verdict, raw = check_once(config, args.workspace, args.task, act=not args.no_act)
    out = verdict.to_dict()
    out["raw_ui_value"] = raw
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _cmd_watch(args, config: Config):
    run(config, args.workspace, args.task, poll_interval=args.interval, once=args.once)


def _cmd_discover(args, config: Config):
    discover_mod.discover(config, apply=getattr(args, "apply", False))


def _cmd_reset(args, config: Config):
    home = config.home
    if args.all:
        removed = 0
        for pat in (".cb_task_*.json", ".cb_ws_*.json", ".cb_state_*.json"):
            for f in glob.glob(os.path.join(home, pat)):
                try:
                    os.remove(f)
                    removed += 1
                except OSError:
                    pass
        print(f"已清空全部累计/状态文件：{removed} 个（下次 watch 从 0 重新累计）")
        return
    ws = args.workspace
    if not ws:
        print("请指定 --workspace <名> 或 --all")
        return
    task = args.task
    names = [os.path.join(home, f".cb_ws_{ws}.json")]
    if task:
        names.append(os.path.join(home, f".cb_task_{ws}_{task}.json"))
        names.append(os.path.join(home, f".cb_state_{ws}_{task}.json"))
    else:
        names.append(os.path.join(home, f".cb_state_{ws}.json"))
        names += glob.glob(os.path.join(home, f".cb_task_{ws}_*.json"))
        names += glob.glob(os.path.join(home, f".cb_state_{ws}_*.json"))
    removed = 0
    for n in names:
        if os.path.isfile(n):
            try:
                os.remove(n)
                removed += 1
            except OSError:
                pass
    tag = f" 任务[{task}]" if task else ""
    print(f"已重置 工作空间[{ws}]{tag}：{removed} 个文件")


def _cmd_status(args, config: Config):
    ws = args.workspace or "_"
    for name in ("_",):  # 仅展示给定工作空间
        path = config.state_file(ws, args.task)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                print(f"状态文件 {path}:")
                print(f.read())
        else:
            print(f"尚无状态文件：{path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="circuit-breaker",
                                description="WorkBuddy 积分熔断工具（UIA/OCR 读取 + 两级熔断）")
    sub = p.add_subparsers(dest="cmd")

    pc = sub.add_parser("check", help="单次检测并打印 verdict（agent 可每轮调用）")
    pc.add_argument("--workspace", required=True)
    pc.add_argument("--task", default=None)
    pc.add_argument("--no-act", action="store_true", help="只检测不触发熔断动作")
    pc.set_defaults(func=_cmd_check)

    pw = sub.add_parser("watch", help="守护轮询（自动检测 + 熔断）")
    pw.add_argument("--workspace", required=True)
    pw.add_argument("--task", default=None)
    pw.add_argument("--interval", type=int, default=None)
    pw.add_argument("--once", action="store_true")
    pw.set_defaults(func=_cmd_watch)

    pd = sub.add_parser("discover", help="只读定位积分元素 + 关闭控件，输出建议 locator")
    pd.add_argument("--apply", action="store_true", help="把建议 locator 写入 config.json")
    pd.set_defaults(func=_cmd_discover)

    pconf = sub.add_parser("config", help="查看/修改配置")
    pconf.add_argument("--show", action="store_true")
    pconf.add_argument("--workspace", default="_")
    pconf.add_argument("--task", default=None)
    pconf.add_argument("--set-workspace-budget", type=int, default=None, dest="set_workspace_budget")
    pconf.add_argument("--set-default-budget", type=int, default=None, dest="set_default_budget")
    pconf.add_argument("--set-task-budget", type=int, default=None, dest="set_task_budget")
    pconf.add_argument("--set-reader-field", choices=["remaining", "used"], default=None)
    pconf.add_argument("--set-keyword", default=None)
    pconf.add_argument("--set-thresholds", nargs=2, type=float, default=None,
                       metavar=("WARN", "TRIP"))
    pconf.set_defaults(func=_cmd_config)

    ps = sub.add_parser("status", help="查看状态文件")
    ps.add_argument("--workspace", default=None)
    ps.add_argument("--task", default=None)
    ps.set_defaults(func=_cmd_status)

    pr = sub.add_parser("reset", help="清空累计/状态文件（消除陈旧高总额导致的误断）")
    pr.add_argument("--workspace", default=None)
    pr.add_argument("--task", default=None)
    pr.add_argument("--all", action="store_true")
    pr.set_defaults(func=_cmd_reset)

    return p


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 1
    config = Config()
    args.func(args, config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
