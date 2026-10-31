-- Извлечение фрагмента
select car_id, specs -> 'engine' as engine
from car
order by car_id;

