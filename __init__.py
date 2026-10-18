"""Magic Hour custom nodes for ComfyUI."""

from . import nodes, nodes_more

NODE_CLASS_MAPPINGS = {**nodes.NODE_CLASS_MAPPINGS, **nodes_more.NODE_CLASS_MAPPINGS}
NODE_DISPLAY_NAME_MAPPINGS = {**nodes.NODE_DISPLAY_NAME_MAPPINGS, **nodes_more.NODE_DISPLAY_NAME_MAPPINGS}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
