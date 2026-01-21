from typing import Any, Dict, List, TypeVar, Union

from aiwin_resource.base import Resource, ResourceContext
from aiwin_resource.plugins.number.v1.main import NumberResource


"""
Schema:
{
    "schema": "numbers.v1",
    "kind": "collection",
    "items": "number.v1",
}
"""

TData = TypeVar('TData', float, int, complex)


class NumbersResource(Resource[List[TData]]):
    """Numbers collection resource implementation."""
    _generate_siblings: bool = False
    _siblings: List[Resource[TData]] = []

    def __init__(self, ctx: Union[ResourceContext, Dict[str, Any]]):
        super().__init__(ctx)
        # 確保 data 是 list 類型
        if not isinstance(self._data, (list, tuple, set)) and self._data is not None:
            raise ValueError(
                f"NumbersResource data must be a list, tuple, or set, got {type(self._data)}")

        self._generate_siblings = ctx.get('generate_siblings', False)
        if (self._generate_siblings and self._data is not None):
            for idx in range(len(self._data)):
                self._siblings.append(NumberResource({
                    'name': f"number_{idx}",
                    'scopes': [*self._scopes, self._name],
                    'data': self._data[idx]
                }))

    def get_sibling_resources(self) -> List[Resource[Any]]:
        return []

    def serialize(self) -> List[Dict[str, Any]]:

        data_list: List[TData] | None = list(
            self._data) if self._data is not None else None

        return [{
            'key': f"{'.'.join(self._scopes)}.{self._name}",
            'schema': 'numbers.v1',
            'kind': 'collection',
            'items': 'number.v1',
            'name': self._name,
            'timestamp': self._timestamp.isoformat(),
            'scopes': self._scopes,
            'data': data_list
        }]

    def from_serialized(self, serialized: Dict[str, Any]) -> 'NumbersResource[TData]':
        return NumbersResource({
            'name': serialized['name'],
            'scopes': serialized['scopes'],
            'data': serialized['data']
        })

    def dispose(self) -> None:
        pass  # no-op

    def set_data(self, data: List[TData]) -> None:
        super().set_data(data)
        if (not self._generate_siblings or self._data is None):
            return

        self._siblings = self._siblings[:len(data)]
        for idx in range(len(data)):
            if (idx < len(self._siblings)):
                self._siblings[idx].set_data(data[idx])
            else:
                self._siblings.append(NumberResource({
                    'name': f"number_{idx}",
                    'scopes': [*self._scopes, self._name],
                    'data': data[idx]
                }))
