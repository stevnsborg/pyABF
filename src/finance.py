import numpy as np


def property_tax(property_value_new: float, 
                 property_value_old: float, 
                 property_tax_rate: float, 
                 year_eval: int):
    """ The property tax calculation of Andelsbolig from 2024 onwards
    The new rules stipulate that the change in the property tax going
    towards the new value cannot increase yearly by more than 4.75% 
    based on the last evaluation prior to the new evaluation. In the
    first year (2024) the tax can only increase by 2.8% of. This will 
    continue untill the new value is reached.

    source: https://www.vurderingsportalen.dk/erhverv/andelsbolig/beskatning/eksempler-grundskyld
    """
    incr = property_value_old*0.028
    res = property_value_old + incr
    property_tax_exit = property_value_new*property_tax_rate*0.8
    terminal_year = int(np.floor((property_tax_exit - res)/(property_tax_exit*0.0475)))

    if year_eval == 2024:
        return res, incr
    elif year_eval < 2024 + terminal_year:
        return res + property_tax_exit*0.0475*(year_eval - 2023 - 1), property_tax_exit*0.0475
    elif year_eval == 2024 + terminal_year:
        return property_tax_exit, property_tax_exit - property_tax_exit*0.0475*(terminal_year)
    else:
        return property_tax_exit, 0


def net_present_value(rent_avg:float,
                      rent_mod:float,
                      cost_mod:float,
                      cost_opr:float,
                      area_mod:float,
                      rent_com:float=0,
                      deduction:float=0,
                      neval:int = 15,
                      options:dict={}
                      ):
    """ The Discount Cash Flow (DCF) model that is used to compute the 
    value of the Andelsbolig.  

    Args:
        rent_avg (float): _description_
        rent_mod (float): _description_
        cost_mod (float): _description_
        cost_opr (float): _description_
        area_mod (float): _description_
        rent_com (float, optional): _description_. Defaults to 0.
        deduction (float, optional): _description_. Defaults to 0.
        neval (int, optional): _description_. Defaults to 15.
        options (dict, optional): _description_. Defaults to {}.

    Returns:
        _type_: _description_
    """

    # optional values
    infl_rate = options.get("infl_rate", 0.02)
    rtrn_rate = options.get("disc_rate", 0.035)
    disc_rate = infl_rate + rtrn_rate
    exec_add = options.get("exec_add", 0)

    # temp variables
    annum_list = np.arange(start=1, stop=neval + 2, step=1, dtype=int)
    balance_sheet = np.zeros((8, neval + 1))
    area_mod_annum = area_mod/neval

    # compute the npv values
    for i in range(0, neval + 1):
        # price adjust based on last year
        infl_adj = ((1 + infl_rate)**(i))
        
        # Compute the cashflow balances
        balance_sheet[0,i] = rent_avg*infl_adj
        balance_sheet[1,i] = rent_mod*infl_adj*area_mod_annum*i if i != area_mod + 1 or i == 0 else area_mod_annum*neval
        balance_sheet[2,i] = rent_com*infl_adj
        balance_sheet[4,i] = -cost_opr*infl_adj
        balance_sheet[5,i] = -cost_mod*infl_adj*area_mod_annum if area_mod_annum*(i+1) <= area_mod else 0
        balance_sheet[6,i] = -exec_add*infl_adj if area_mod_annum*(i+1) <= area_mod else 0
        balance_sheet[7,i] = -deduction*infl_adj

    # Compute the NPV cash flow w. exit value
    cash_flow = balance_sheet.sum(axis=0)
    npv_cf = sum((cash_flow/((1 + disc_rate)**annum_list))[0:-1])
    npv_exit = cash_flow[-1]/(disc_rate - infl_rate)/((1 + disc_rate)**(neval))
    return (npv_cf, npv_exit, balance_sheet)
