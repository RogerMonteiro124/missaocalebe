from datetime import datetime, timedelta

def get_next_14_days(start_date):
    dates = []
    current_date = datetime.strptime(start_date, '%d-%m-%Y')

    for _ in range(16):
        dates.append(current_date.strftime('%d-%m-%Y'))
        current_date += timedelta(days=1)

    return dates
def obter_data_do_sorteio(start_date, dia):
    print(start_date, dia)
    current_date = datetime.strptime(start_date, '%d-%m-%Y')
    delta = timedelta(days=int(dia)-1)
    data_sorteio = current_date + delta
    return data_sorteio.strftime('%d-%m-%Y')
      