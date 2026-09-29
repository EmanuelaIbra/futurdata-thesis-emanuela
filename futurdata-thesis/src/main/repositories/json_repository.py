"""JSON persistence repository for ARIADNE.

This module is the persistence boundary of the application.  The UI and models do
not know how data is stored; they talk to this repository through the controller.
All persistent application data lives in one human-readable JSON document.
"""
from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional, Tuple


class DuplicateValueError(ValueError):
    """Raised when a catalog value that must be unique already exists."""


class JsonRepository:
    _INTERMEDIATE_OFFSET = 1_000_000
    _LEAF_OFFSET = 2_000_000

    COLLECTIONS = (
        "colors", "material_categories", "material_subcategories", "material_types",
        "materials", "tools", "actions", "root_components", "intermediate_components",
        "leaf_components", "disassembly_steps", "disassembly_step_actions",
        "step_output_intermediate", "step_output_leaf",
    )

    def __init__(self, file_path: str | None = None):
        app_dir = Path("D:/.disassembly_diagram")
        app_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = Path(file_path) if file_path else app_dir / "ariadne_data.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._data = self._load_or_create()

    # ---------- storage ----------
    def _empty_data(self) -> Dict[str, Any]:
        data = {"schema_version": 1, "updated_at": datetime.now().isoformat(), "counters": {}}
        for name in self.COLLECTIONS:
            data[name] = []
            data["counters"][name] = 0
        return data

    def _load_or_create(self) -> Dict[str, Any]:
        if self.file_path.exists():
            try:
                with self.file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                for name in self.COLLECTIONS:
                    data.setdefault(name, [])
                data.setdefault("counters", {})
                for name in self.COLLECTIONS:
                    data["counters"][name] = max(
                        int(data["counters"].get(name, 0)),
                        max((int(x.get("id", 0)) for x in data[name]), default=0),
                    )
                return data
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                backup = self.file_path.with_suffix(self.file_path.suffix + ".broken")
                try:
                    self.file_path.replace(backup)
                except OSError:
                    pass
        data = self._empty_data()
        self._seed_defaults(data)
        self._write(data)
        return data

    def _write(self, data: Optional[Dict[str, Any]] = None) -> None:
        payload = data if data is not None else self._data
        payload["updated_at"] = datetime.now().isoformat()
        fd, temp_name = tempfile.mkstemp(prefix="ariadne_", suffix=".json", dir=str(self.file_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self.file_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _save(self) -> None:
        with self._lock:
            self._write()

    def _next_id(self, collection: str) -> int:
        self._data["counters"][collection] = int(self._data["counters"].get(collection, 0)) + 1
        return self._data["counters"][collection]

    def _insert(self, collection: str, values: Dict[str, Any]) -> int:
        row = dict(values)
        row["id"] = self._next_id(collection)
        self._data[collection].append(row)
        self._save()
        return row["id"]

    def _find(self, collection: str, row_id: int) -> Optional[Dict[str, Any]]:
        return next((x for x in self._data[collection] if int(x.get("id", -1)) == int(row_id)), None)

    def _update(self, collection: str, row_id: int, updates: Dict[str, Any]) -> bool:
        row = self._find(collection, row_id)
        if not row:
            return False
        row.update(updates)
        self._save()
        return True

    def _delete(self, collection: str, row_id: int) -> bool:
        before = len(self._data[collection])
        self._data[collection] = [x for x in self._data[collection] if int(x.get("id", -1)) != int(row_id)]
        changed = len(self._data[collection]) != before
        if changed:
            self._save()
        return changed

    def _seed_defaults(self, data: Dict[str, Any]) -> None:
        def add(collection, **values):
            data["counters"][collection] += 1
            data[collection].append({"id": data["counters"][collection], **values})

        for name, hx, r, g, b in [
            ("Red", "#FF0000", 255, 0, 0), ("Green", "#00FF00", 0, 255, 0),
            ("Blue", "#0000FF", 0, 0, 255), ("Black", "#000000", 0, 0, 0),
            ("White", "#FFFFFF", 255, 255, 255), ("Yellow", "#FFFF00", 255, 255, 0),
            ("Orange", "#FFA500", 255, 165, 0), ("Gray", "#808080", 128, 128, 128),
            ("Silver", "#C0C0C0", 192, 192, 192), ("Brown", "#8B4513", 139, 69, 19),
            ("Pink", "#FFC0CB", 255, 192, 203), ("Purple", "#800080", 128, 0, 128),
            ("Cyan", "#00FFFF", 0, 255, 255), ("Gold", "#FFD700", 255, 215, 0),
            ("Transparent", "#000000", 0, 0, 0),
        ]:
            add("colors", name=name, hex_code=hx, rgb_r=r, rgb_g=g, rgb_b=b)
        cats = ["Plastic", "Metal", "Glass", "Ceramic", "Composite", "Wood", "Rubber", "Textile"]
        for name in cats:
            add("material_categories", name=name)
        subs = [(1,"Thermoplastic"),(1,"Thermoset"),(2,"Ferrous"),(2,"Non-Ferrous"),(3,"Tempered"),(3,"Laminated"),(4,"Porcelain"),(4,"Earthenware"),(5,"Fiber-Reinforced"),(5,"Particle"),(6,"Hardwood"),(6,"Softwood"),(7,"Natural"),(7,"Synthetic"),(8,"Natural Fiber"),(8,"Synthetic Fiber")]
        for category_id, name in subs:
            add("material_subcategories", category_id=category_id, name=name)
        types = [(1,1,"ABS"),(1,1,"PET"),(1,1,"PP"),(1,1,"PVC"),(1,2,"Epoxy"),(1,2,"Polyester"),(2,3,"Steel"),(2,3,"Cast Iron"),(2,4,"Aluminum"),(2,4,"Copper"),(2,4,"Brass"),(2,None,"Titanium")]
        for category_id, subcategory_id, name in types:
            add("material_types", category_id=category_id, subcategory_id=subcategory_id, name=name)
        for name, scientific in [("Plastic","PC"),("Metal","N/A"),("Glass","N/A"),("Rubber","N/A"),("Wood","N/A"),("Composite","N/A"),("Ceramic","N/A"),("PCB","N/A"),("Other","N/A")]:
            add("materials", name=name, category_id=None, subcategory_id=None, type_id=None, scientific_name=scientific, technical_name=scientific, surface="")

    # ---------- ids ----------
    def _encode_component_id(self, table_name: str, row_id: int) -> int:
        if table_name == "root_component": return row_id
        if table_name == "intermediate_component": return self._INTERMEDIATE_OFFSET + row_id
        if table_name == "leaf_component": return self._LEAF_OFFSET + row_id
        raise ValueError(f"Unsupported component table: {table_name}")

    def _decode_component_id(self, component_id: int) -> Tuple[str, int]:
        component_id = int(component_id)
        if component_id >= self._LEAF_OFFSET: return "leaf_component", component_id - self._LEAF_OFFSET
        if component_id >= self._INTERMEDIATE_OFFSET: return "intermediate_component", component_id - self._INTERMEDIATE_OFFSET
        return "root_component", component_id

    @staticmethod
    def _collection_for_table(table: str) -> str:
        return {"root_component":"root_components", "intermediate_component":"intermediate_components", "leaf_component":"leaf_components"}[table]

    # ---------- products/components ----------
    def create_product(self, name: str, brand: str = "", model: str = "", description: str = "", x: float = 400, y: float = 100) -> int:
        now = datetime.now().isoformat()
        return self._insert("root_components", {"name":name,"brand":brand,"model":model,"description":description,"created_at":now,"modified_at":now,"color_id":None,"material_id":None,"weight":None,"weight_unit":"g","node_type":"Root","image_path":""})

    def get_product(self, product_id: int):
        row = self._find("root_components", product_id)
        return copy.deepcopy(row) if row else None

    def find_root_by_name(self, name: str):
        row = next((x for x in self._data["root_components"] if x.get("name") == name), None)
        return copy.deepcopy(row) if row else None

    def get_all_products(self):
        return sorted(copy.deepcopy(self._data["root_components"]), key=lambda x: x.get("modified_at", ""), reverse=True)

    def update_product(self, product_id: int, **kwargs):
        allowed={"name","brand","model","description","color_id","material_id","weight","weight_unit","node_type","image_path"}
        updates={k:v for k,v in kwargs.items() if k in allowed}; updates["modified_at"]=datetime.now().isoformat()
        return self._update("root_components", product_id, updates)

    def delete_product(self, product_id: int):
        if not self._find("root_components", product_id): return False
        component_ids = [self._encode_component_id("intermediate_component", x["id"]) for x in self._data["intermediate_components"] if x.get("root_component_id")==product_id]
        component_ids += [self._encode_component_id("leaf_component", x["id"]) for x in self._data["leaf_components"] if x.get("root_component_id")==product_id]
        for cid in component_ids: self.delete_component(cid)
        root_steps=[x["id"] for x in self._data["disassembly_steps"] if x.get("input_root_component_id")==product_id]
        for sid in root_steps: self.delete_step(sid)
        return self._delete("root_components", product_id)

    def create_component(self, name: str, product_id: int=None, color_id: int=None, material_id: int=None, weight: float=None, weight_unit: str="g", node_type: str="", x: float=0, y: float=0):
        normalized=(node_type or "Intermediate").strip().lower()
        if normalized in ("root","product"):
            rid=self.create_product(name); self.update_component(rid, weight=weight, weight_unit=weight_unit, node_type="Root"); return rid
        table="leaf_component" if normalized=="leaf" else "intermediate_component"
        if product_id is None: raise ValueError("product_id (root component id) is required")
        collection=self._collection_for_table(table)
        if table=="intermediate_component": color_id=material_id=None
        rid=self._insert(collection,{"root_component_id":int(product_id),"color_id":color_id,"material_id":material_id,"name":name,"weight":weight,"weight_unit":weight_unit,"node_type":"Leaf" if table=="leaf_component" else "Intermediate","image_path":""})
        return self._encode_component_id(table,rid)

    def _decorate_component(self, table: str, row: Dict[str,Any]):
        data=copy.deepcopy(row); encoded=self._encode_component_id(table,row["id"]); data["id"]=encoded; data["component_id"]=encoded; data["source_table"]=table
        color=self.get_color(row.get("color_id")) if row.get("color_id") else None; material=self.get_material(row.get("material_id")) if row.get("material_id") else None
        data["color_name"]=color.get("name") if color else None; data["hex_code"]=color.get("hex_code") if color else None; data["material_name"]=material.get("name") if material else None; data["material_scientific_name"]=material.get("scientific_name") if material else None
        return data

    def get_component(self, component_id: int):
        table,rid=self._decode_component_id(component_id); row=self._find(self._collection_for_table(table),rid)
        return self._decorate_component(table,row) if row else None

    def get_components_by_product(self, product_id: int):
        out=[]
        for table in ("intermediate_component","leaf_component"):
            for row in self._data[self._collection_for_table(table)]:
                if int(row.get("root_component_id",-1))==int(product_id): out.append(self._decorate_component(table,row))
        return out

    def get_root_component(self, product_id: int): return self.get_component(product_id)

    def update_component(self, component_id: int, **kwargs):
        table,rid=self._decode_component_id(component_id); allowed={"name","weight","weight_unit","node_type","image_path","brand","model","description"}
        if table=="leaf_component": allowed |= {"color_id","material_id","root_component_id"}
        elif table=="intermediate_component": allowed |= {"root_component_id"}
        updates={k:v for k,v in kwargs.items() if k in allowed}
        if "weight" in updates: updates["weight"] = float(updates["weight"]) if updates["weight"] is not None and str(updates["weight"]).strip() else None
        if table=="root_component": updates["modified_at"]=datetime.now().isoformat()
        return self._update(self._collection_for_table(table),rid,updates)

    def delete_component(self, component_id: int):
        table,rid=self._decode_component_id(component_id); collection=self._collection_for_table(table)
        if not self._find(collection,rid): return False
        if table=="root_component": return self.delete_product(rid)
        for sid in [x["id"] for x in self._data["disassembly_steps"] if x.get("input_intermediate_component_id")==rid or x.get("input_leaf_component_id")==rid]: self.delete_step(sid)
        self._data["step_output_intermediate"]=[x for x in self._data["step_output_intermediate"] if not(table=="intermediate_component" and x.get("intermediate_component_id")==rid)]
        self._data["step_output_leaf"]=[x for x in self._data["step_output_leaf"] if not(table=="leaf_component" and x.get("leaf_component_id")==rid)]
        return self._delete(collection,rid)

    # ---------- catalogs ----------
    def get_all_colors(self): return sorted(copy.deepcopy(self._data["colors"]), key=lambda x:x["name"])
    def get_color(self,color_id):
        if color_id is None:return None
        row=self._find("colors",color_id); return copy.deepcopy(row) if row else None
    def create_color(self,name,hex_code,rgb_r=0,rgb_g=0,rgb_b=0):
        name=(name or "").strip(); hex_code=(hex_code or "").strip()
        if not name: raise ValueError("Color name is required.")
        if any(x["name"].lower()==name.lower() for x in self._data["colors"]): raise DuplicateValueError("Color already exists.")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}",hex_code): raise ValueError("Hex code must be #RRGGBB.")
        return self._insert("colors",{"name":name,"hex_code":hex_code,"rgb_r":int(rgb_r),"rgb_g":int(rgb_g),"rgb_b":int(rgb_b)})
    def delete_color(self,color_id): return self._delete("colors",color_id)

    def get_all_material_categories(self): return sorted(copy.deepcopy(self._data["material_categories"]),key=lambda x:x["name"])
    def create_material_category(self,name):
        name=(name or "").strip()
        if any(x["name"].lower()==name.lower() for x in self._data["material_categories"]): raise DuplicateValueError("Category already exists.")
        return self._insert("material_categories",{"name":name})
    def get_subcategories_by_category(self,category_id): return sorted([copy.deepcopy(x) for x in self._data["material_subcategories"] if x.get("category_id")==int(category_id)],key=lambda x:x["name"])
    def create_material_subcategory(self,category_id,name): return self._insert("material_subcategories",{"category_id":int(category_id),"name":(name or "").strip()})
    def get_types_by_category(self,category_id,subcategory_id=None): return sorted([copy.deepcopy(x) for x in self._data["material_types"] if x.get("category_id")==int(category_id) and x.get("subcategory_id")==subcategory_id],key=lambda x:x["name"])
    def create_material_type(self,category_id,name,subcategory_id=None): return self._insert("material_types",{"category_id":int(category_id),"subcategory_id":subcategory_id,"name":(name or "").strip()})

    def _decorate_material(self,row):
        d=copy.deepcopy(row); cat=self._find("material_categories",row.get("category_id")) if row.get("category_id") else None; sub=self._find("material_subcategories",row.get("subcategory_id")) if row.get("subcategory_id") else None; typ=self._find("material_types",row.get("type_id")) if row.get("type_id") else None
        d.update(category_name=cat.get("name") if cat else None,subcategory_name=sub.get("name") if sub else None,type_name=typ.get("name") if typ else None); return d
    def create_material(self,name,category_id=None,subcategory_id=None,type_id=None,technical_name="",surface=""):
        return self._insert("materials",{"name":(name or "").strip(),"category_id":category_id,"subcategory_id":subcategory_id,"type_id":type_id,"scientific_name":technical_name or "","technical_name":technical_name or "","surface":surface or ""})
    def get_material(self,material_id):
        if material_id is None:return None
        row=self._find("materials",material_id); return self._decorate_material(row) if row else None
    def get_all_materials(self): return sorted([self._decorate_material(x) for x in self._data["materials"]],key=lambda x:x["name"])
    def update_material(self,material_id,**kwargs): return self._update("materials",material_id,{k:v for k,v in kwargs.items() if k in {"name","category_id","subcategory_id","type_id","technical_name","surface"}})
    def delete_material(self,material_id): return self._delete("materials",material_id)
    def get_material_display_name(self,material_id):
        m=self.get_material(material_id)
        if not m:return "Unknown"
        return " > ".join([x for x in [m.get("category_name"),m.get("subcategory_name"),m.get("type_name"),m.get("name")] if x])

    def create_tool(self,name,category=""):
        name=(name or "").strip(); existing=next((x for x in self._data["tools"] if x["name"].lower()==name.lower()),None)
        return existing["id"] if existing else self._insert("tools",{"name":name,"category":(category or "").strip()})
    def get_tool(self,tool_id):
        row=self._find("tools",tool_id); return copy.deepcopy(row) if row else None
    def get_all_tools(self): return sorted(copy.deepcopy(self._data["tools"]),key=lambda x:(x.get("category",""),x.get("name","")))
    def delete_tool(self,tool_id): return self._delete("tools",tool_id)

    # ---------- steps/actions/relations ----------
    def create_step(self, component_id:int, step_order:int, description:str="", image_path:str="", action_id:int=None, title:str=""):
        table,rid=self._decode_component_id(component_id)
        row={"input_root_component_id":rid if table=="root_component" else None,"input_intermediate_component_id":rid if table=="intermediate_component" else None,"input_leaf_component_id":rid if table=="leaf_component" else None,"step_order":int(step_order),"title":title,"description":description,"image_path":image_path}
        sid=self._insert("disassembly_steps",row)
        if action_id is not None:self.add_action_to_step(sid,action_id)
        return sid
    def get_steps_for_component(self,component_id:int):
        table,rid=self._decode_component_id(component_id); key={"root_component":"input_root_component_id","intermediate_component":"input_intermediate_component_id","leaf_component":"input_leaf_component_id"}[table]
        return sorted([copy.deepcopy(x) for x in self._data["disassembly_steps"] if x.get(key)==rid],key=lambda x:x.get("step_order",0))
    def get_next_step_order(self,component_id):
        steps=self.get_steps_for_component(component_id); return max([x.get("step_order",0) for x in steps],default=0)+1
    def get_step(self,step_id):
        row=self._find("disassembly_steps",step_id); return copy.deepcopy(row) if row else None
    def get_step_for_component(self,component_id):
        rows=self.get_steps_for_component(component_id); return rows[0] if rows else None
    def update_step(self,step_id,**kwargs):
        updates={k:v for k,v in kwargs.items() if k in {"step_order","title","description","image_path"}}
        if "component_id" in kwargs:
            table,rid=self._decode_component_id(kwargs["component_id"]); updates.update(input_root_component_id=rid if table=="root_component" else None,input_intermediate_component_id=rid if table=="intermediate_component" else None,input_leaf_component_id=rid if table=="leaf_component" else None)
        changed=self._update("disassembly_steps",step_id,updates) if updates else False
        if kwargs.get("action_id") is not None:
            self._data["disassembly_step_actions"]=[x for x in self._data["disassembly_step_actions"] if x.get("disassembly_step_id")!=int(step_id)]; self._save(); self.add_action_to_step(step_id,kwargs["action_id"]); changed=True
        return changed
    def delete_step(self,step_id):
        self._data["disassembly_step_actions"]=[x for x in self._data["disassembly_step_actions"] if x.get("disassembly_step_id")!=int(step_id)]
        self._data["step_output_intermediate"]=[x for x in self._data["step_output_intermediate"] if x.get("disassembly_step_id")!=int(step_id)]
        self._data["step_output_leaf"]=[x for x in self._data["step_output_leaf"] if x.get("disassembly_step_id")!=int(step_id)]
        return self._delete("disassembly_steps",step_id)
    def get_component_root_component_id(self,component_id):
        table,rid=self._decode_component_id(component_id)
        if table=="root_component":return rid
        row=self._find(self._collection_for_table(table),rid); return row.get("root_component_id") if row else None
    def get_step_root_component_id(self,step_id):
        step=self.get_step(step_id)
        if not step:return None
        if step.get("input_root_component_id") is not None:return step["input_root_component_id"]
        if step.get("input_intermediate_component_id") is not None:return self.get_component_root_component_id(self._encode_component_id("intermediate_component",step["input_intermediate_component_id"]))
        if step.get("input_leaf_component_id") is not None:return self.get_component_root_component_id(self._encode_component_id("leaf_component",step["input_leaf_component_id"]))
    def create_action(self,name,description="",tool_id=None,next_action_id=None,x=0,y=0): return self._insert("actions",{"name":name,"description":description,"tool_id":tool_id,"image_path":""})
    def get_action(self,action_id):
        row=self._find("actions",action_id)
        if not row:return None
        d=copy.deepcopy(row); tool=self.get_tool(row.get("tool_id")) if row.get("tool_id") else None; d["tool_name"]=tool.get("name") if tool else None; d["tool_category"]=tool.get("category") if tool else None; return d
    def get_action_chain(self,action_id):
        action=self.get_action(action_id); return [action] if action else []
    def update_action(self,action_id,**kwargs): return self._update("actions",action_id,{k:v for k,v in kwargs.items() if k in {"name","description","tool_id","image_path"}})
    def delete_action(self,action_id):
        self._data["disassembly_step_actions"]=[x for x in self._data["disassembly_step_actions"] if x.get("action_id")!=int(action_id)]
        return self._delete("actions",action_id)
    def get_next_action_order(self,step_id): return max([x.get("action_order",0) for x in self._data["disassembly_step_actions"] if x.get("disassembly_step_id")==int(step_id)],default=0)+1
    def add_action_to_step(self,step_id,action_id,action_order=None):
        existing=next((x for x in self._data["disassembly_step_actions"] if x.get("disassembly_step_id")==int(step_id) and x.get("action_id")==int(action_id)),None)
        if existing:return {"link_id":existing["id"],"action_order":existing["action_order"],"already_linked":True}
        order=self.get_next_action_order(step_id); lid=self._insert("disassembly_step_actions",{"disassembly_step_id":int(step_id),"action_id":int(action_id),"action_order":order}); return {"link_id":lid,"action_order":order,"already_linked":False}
    def get_actions_for_step(self,step_id):
        links=sorted([x for x in self._data["disassembly_step_actions"] if x.get("disassembly_step_id")==int(step_id)],key=lambda x:x.get("action_order",0)); out=[]
        for link in links:
            action=self.get_action(link["action_id"])
            if action: out.append({"link_id":link["id"],"action_order":link["action_order"],"step_id":int(step_id),"action_id":action["id"],"action":action})
        return out
    def add_component_to_step(self,step_id,component_id):
        table,rid=self._decode_component_id(component_id)
        if table=="root_component":raise ValueError("Root component cannot be a step output")
        if self.get_step_root_component_id(step_id)!=self.get_component_root_component_id(component_id):raise ValueError("Output component belongs to another root component")
        collection="step_output_intermediate" if table=="intermediate_component" else "step_output_leaf"; key="intermediate_component_id" if table=="intermediate_component" else "leaf_component_id"
        existing=next((x for x in self._data[collection] if x.get("disassembly_step_id")==int(step_id) and x.get(key)==rid),None)
        if existing:return {"link_id":existing["id"],"already_linked":True}
        lid=self._insert(collection,{"disassembly_step_id":int(step_id),key:rid}); return {"link_id":lid,"already_linked":False}
    def get_components_from_step(self,step_id):
        out=[]
        for link in self._data["step_output_intermediate"]:
            if link.get("disassembly_step_id")==int(step_id):
                c=self.get_component(self._encode_component_id("intermediate_component",link["intermediate_component_id"])); out.append(c) if c else None
        for link in self._data["step_output_leaf"]:
            if link.get("disassembly_step_id")==int(step_id):
                c=self.get_component(self._encode_component_id("leaf_component",link["leaf_component_id"])); out.append(c) if c else None
        return out
    def remove_component_from_step(self,step_id,component_id):
        table,rid=self._decode_component_id(component_id); collection="step_output_intermediate" if table=="intermediate_component" else "step_output_leaf"; key="intermediate_component_id" if table=="intermediate_component" else "leaf_component_id"
        before=len(self._data[collection]); self._data[collection]=[x for x in self._data[collection] if not(x.get("disassembly_step_id")==int(step_id) and x.get(key)==rid)]; changed=len(self._data[collection])!=before
        if changed:self._save()
        return changed

    # ---------- dynamic UI schema ----------
    _SCHEMAS={
        "root_component":[("id","INTEGER"),("name","TEXT"),("brand","TEXT"),("model","TEXT"),("description","TEXT"),("created_at","TEXT"),("modified_at","TEXT"),("color_id","INTEGER"),("material_id","INTEGER"),("weight","REAL"),("weight_unit","TEXT"),("node_type","TEXT"),("image_path","TEXT")],
        "intermediate_component":[("id","INTEGER"),("root_component_id","INTEGER"),("color_id","INTEGER"),("material_id","INTEGER"),("name","TEXT"),("weight","REAL"),("weight_unit","TEXT"),("node_type","TEXT"),("image_path","TEXT")],
        "leaf_component":[("id","INTEGER"),("root_component_id","INTEGER"),("color_id","INTEGER"),("material_id","INTEGER"),("name","TEXT"),("weight","REAL"),("weight_unit","TEXT"),("node_type","TEXT"),("image_path","TEXT")],
        "action":[("id","INTEGER"),("name","TEXT"),("description","TEXT"),("tool_id","INTEGER"),("image_path","TEXT")],
        "disassembly_step":[("id","INTEGER"),("input_root_component_id","INTEGER"),("input_intermediate_component_id","INTEGER"),("input_leaf_component_id","INTEGER"),("step_order","INTEGER"),("title","TEXT"),("description","TEXT"),("image_path","TEXT")],
        "material":[("id","INTEGER"),("category_id","INTEGER"),("subcategory_id","INTEGER"),("type_id","INTEGER"),("name","TEXT"),("scientific_name","TEXT"),("technical_name","TEXT"),("surface","TEXT")],
    }
    def get_table_schema(self,table_name): return [{"cid":i,"name":n,"type":t,"notnull":False,"default":None,"pk":n=="id"} for i,(n,t) in enumerate(self._SCHEMAS.get(table_name,[]))]
    def _fields(self,table,exclude):
        out=[]
        for col in self.get_table_schema(table):
            if col["name"] in exclude:continue
            col["display_name"]=col["name"].replace("_"," ").title()
            if col["name"] in {"color_id","material_id"}: col["widget_type"]="dropdown"; col["display_name"]={"color_id":"Color","material_id":"Material","tool_id":"Tool"}[col["name"]]
            if col["name"] == "tool_id":
                col["widget_type"] = "text"
                col["display_name"] = "Tool / Function"
            out.append(col)
        return out
    def get_component_fields(self,component_kind="intermediate"):
        kind=(component_kind or "intermediate").lower(); table="root_component" if kind=="root" else "leaf_component" if kind=="leaf" else "intermediate_component"; exclude={"id","created_at","modified_at","color_id","material_id"} if kind=="root" else {"id","root_component_id"} if kind=="leaf" else {"id","root_component_id","color_id","material_id"}; return self._fields(table,exclude)
    def get_product_fields(self): return self._fields("root_component",{"id","created_at","modified_at","node_type"})
    def get_action_fields(self): return self._fields("action",{"id"})
    def get_step_fields(self): return self._fields("disassembly_step",{"id","input_root_component_id","input_intermediate_component_id","input_leaf_component_id","step_order"})
    def get_material_fields(self): return self._fields("material",{"id"})
    def get_statistics(self): return {name:len(self._data[name]) for name in self.COLLECTIONS}

    def export_snapshot(self): return copy.deepcopy(self._data)

_default_repository: Optional[JsonRepository] = None
def get_repository(file_path: str | None = None) -> JsonRepository:
    global _default_repository
    if _default_repository is None or (file_path and str(_default_repository.file_path)!=str(Path(file_path))): _default_repository=JsonRepository(file_path)
    return _default_repository
