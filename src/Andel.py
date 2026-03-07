from .utils import _UNIT, _NOTE


class Andel(_UNIT):
    price: float = None
    price_area: float = None
    def __init__(self, address:str, area:float, rooms:int):
        super().__init__(address, area, rooms)

    def update_price(self, new_area_price):
        self.price_area = new_area_price
        self.price = new_area_price*self.area
        return self.price


class Commercial(_UNIT):
    def __init__(self, address:str, area:float, rooms:int):
        super().__init__(address, area, rooms)


class Improvement:
    
    def __init__(self, _id:str, year:int, price:float, improvement_factor:float=1.0, improvement_percentage:float=0.10):
        self._id = _id
        self.year = year
        self.price = price
        self.imp_fact = improvement_factor
        self.imp_perc = improvement_percentage
        
        # the quantified value addition
        self.imp_value = self.price*self.imp_fact*self.imp_perc




class AndelsBolig:   

    """ This is a class to store the 

    Returns:
        _type_: _description_
    """
    
    area_res = 0
    area_com = 0
    area_tot = 0

    # book tabs 
    _NOTE_01 = _NOTE(_id="01")    # Income    
    _NOTE_02 = _NOTE(_id="02")    # Personel expenses  
    _NOTE_03 = _NOTE(_id="03")    # Insurances and subscriptions
    _NOTE_04 = _NOTE(_id="04")    # Taxes and Utility Costs
    _NOTE_05 = _NOTE(_id="05")    # Cleaning
    _NOTE_06 = _NOTE(_id="06")    # Maintenance
    _NOTE_07 = _NOTE(_id="07")    # Reconstruction
    _NOTE_08 = _NOTE(_id="08")    # Administration
    _NOTE_09 = _NOTE(_id="09")    # Amortizations
    _NOTE_10 = _NOTE(_id="10")    # Financial costs


    def __init__(self, 
                 andele:list[Andel], 
                 commercial: list[Commercial] = []):
        
        """_summary_
        """

        # accumulate areas
        self.andele = andele
        for andel in andele:
            self.area_res += andel.area        
        for comer in commercial:
            self.area_com += comer.area
        self.area_tot = self.area_com + self.area_res

        # load the webscraber to query data ?


