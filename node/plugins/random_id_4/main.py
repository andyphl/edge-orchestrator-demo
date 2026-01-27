from typing import Any, Callable, Dict, Mapping

from aiwin_resource.base import Resource
from node.base import BaseNode, BaseNodeContext
import ast

"""
Example:
{
  "id": "node_1",
  "name": "cast_resource",
  "version": "v1.0.0",
  "config": {
    "source": "node_1.some_unknown_resource",
    "name": "casted_string",
    "target_schema": "string.v1",
    "cast_fn": "def cast_fn(data: Any) -> str: return str(data)"
  }
}
"""

ALLOWED_NODES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.BinOp,
    ast.Mult,
    ast.Add,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Import,
    ast.Call
)


class CastResourceNode(BaseNode):
    _unknown_resource: Resource[Any] | None = None
    _target_schema: str | None = None

    def __init__(self, ctx: BaseNodeContext, config: Dict[str, Any]):
        self.ctx = ctx
        self.cfg = config

    def prepare(self) -> None:
        pass

    def setup(self, config: Dict[str, Any]) -> None:
        pass

    def execute(self) -> Any:
        cfg = self.cfg['config']
        source = cfg['source']
        name = cfg['name']
        target_schema = cfg['target_schema']
        cast_fn_str = cfg['cast_fn']
        cast_fn_tree = ast.parse(cast_fn_str, mode="exec")
        for node in ast.walk(cast_fn_tree):
            if not isinstance(node, ALLOWED_NODES):
                raise ValueError(f"Not allowed syntax: {type(node).__name__}")
        compiled = compile(cast_fn_tree, filename="<user_code>", mode="exec")

        scope: Mapping[str, Any] = {}
        exec(compiled, {}, scope)
        cast_fn: Callable[[Any], Any] | None = scope['cast_fn']

        if (cast_fn is None):
            raise ValueError("cast_fn is not found")
        # Here we handle casting to StringResource as an example
        if target_schema == "string.v1":
            source_resource = self.ctx['resource_manager'].get(source)
            if source_resource is None:
                raise ValueError(f"Source resource {source} not found")
            data = source_resource.get_data()
            casted_data = data if data is None else cast_fn(data)
            casted_resource = self.ctx['resource_creator'].create('string.v1', {
                'name': name,
                'scopes': [self.cfg['id']],
                'data': casted_data
            })
            self.ctx['resource_manager'].set(
                casted_resource.get_key(), casted_resource)

    def next(self) -> None:
        next_node_index = self.cfg.get('_next_node_index')
        next_index = next_node_index if next_node_index is not None else 0  # 最後一節點循環回 0
        self.ctx['event_queue'].put({"next_node_index": next_index})

    def dispose(self) -> None:
        pass
