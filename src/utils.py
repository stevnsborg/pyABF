class _NOTE:
    total:float = 0
    items:dict = {}
    def __init__(self, _id:str, expense:bool):
        self._id = _id
        self.expense = expense

    def add_item(self, item_id:str, item_value:float):
        self.items.update({item_id:item_value})
        self.total = sum(self.items.values())
    
    def rmv_item(self, item_id:str):
        if item_id in self.items.keys():
            del self.items[item_id]
            self.total = sum(self.items.values())


class _UNIT:
    def __init__(self, address:str, area:float, rooms:int, rental:bool=False):
        self.address = address 
        self.area = area
        self.rooms = rooms
        self.rental = rental


class YearReport:
    groups = []
    def __init__(self, year:int):
        self.year = year
    
    # create the note from a custom dicts
    def add_group(self, group:str, content:dict, expenses:bool):
        _note = _NOTE(_id=group, expense=expenses)
        for key, value in content.items:
            _note.add_item(item_id=key, item_value=value)
        self.groups.append(_note)

    # add the year report together
    def compile_year_report(self):
        self.groups
        
        return
