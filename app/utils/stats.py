import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from datetime import datetime, timedelta
from app.database import db
from app.database import repositories

class stat_params:
    days = 20
    width = 10

def splitting(number):
    if number == 0:
        return ""
    return str(round(number/1000, 1)) + 'k'


async def audit_stat(today: datetime, ref: str = None) -> str:
    day = timedelta(days=1)

    offset1 = today + day
    offset2 = today
    count_active = []
    count_not = []
    params = {}

    if ref:
        params['ref'] = ref

    for _ in range(stat_params.days):
        async with db.get_session() as session:
            user_repo = repositories.UserRepository(session)
            count = await user_repo.get_count_users_offsets(offset1, offset2, block_date=None, **params)
            count2 = await user_repo.get_count_users_offsets(offset1, offset2, block_date=True, **params)
        count_active.append(count)
        count_not.append(count2)
        offset1 = offset2
        offset2 -= day

    data = count_active[::-1]
    data2 = count_not[::-1]

    color1 = '#645fd5'
    color2 = '#ae1311'

    plt.style.use('ggplot')
    fig, ax = plt.subplots(figsize=(stat_params.width, 6), facecolor='white', dpi=100)
    max_value = max(data)
    ax.set_ylim((-max_value / 100 * 5, max_value + max_value / 100 * 10))

    ax.set_title(f'Статистика за последние {len(data)} дней', fontsize=20, fontweight='bold')
    ax.set_ylabel('Количество новой аудитории', fontsize=12)

    dts_result = ['Сегодня', 'Вчера']
    datetime_offset = today - day * 2
    for _ in range(len(data) - 2):
        dts_result.append(datetime_offset.strftime('%d.%m'))
        datetime_offset -= day

    plt.xticks(range(len(data)), dts_result[::-1], rotation=45, horizontalalignment='right', fontsize=10)

    offset = -0.1
    bars1 = ax.bar([i + offset for i in range(len(data))], data, color=color1, width=0.4, alpha=0.8, edgecolor='black')
    for i, cty in enumerate(data):
        ax.text(i + offset, cty + (max_value / 100 * 2), splitting(cty), horizontalalignment='center', color=color1, fontsize=10)

    offset = 0.3
    bars2 = ax.bar([i + offset for i in range(len(data2))], data2, color=color2, width=0.2, alpha=0.8, edgecolor='black')
    for i, cty in enumerate(data2):
        ax.text(i + offset, -(max_value / 100 * 3), splitting(cty), horizontalalignment='center', color=color2, fontsize=8, alpha=0.8)

    ax.legend(handles=(
        mpatches.Patch(color=color1, label='Живые', edgecolor='black'),
        mpatches.Patch(color=color2, label='Блок', edgecolor='black'),
    ), fontsize=10)

    ax.text(0.5, 0.5, 'dev by @bandicuttt', fontsize=50, color='gray', alpha=0.5, ha='center', va='center', transform=ax.transAxes)
    
    ax.yaxis.grid(True, linestyle='--', alpha=0.7)

    path = 'app/static/audit_stat.png'
    plt.tight_layout()
    plt.savefig(path)
    plt.close(fig)
    return path