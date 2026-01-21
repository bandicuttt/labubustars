from app import templates

main_admin = {'keyboard': [
    [
        {'text': templates.button_texts.admin_stats_button}, 
        {'text': templates.button_texts.admin_adverts_button},
    ],
    [
        {'text': templates.button_texts.admin_subscribes_button}, 
        {'text': templates.button_texts.admin_referrals_button},
    ],
    [
        {'text': templates.button_texts.admin_backup_button}, 
        {'text': templates.button_texts.admin_mailings_button},
    ],
    [
        {'text': templates.button_texts.admin_promocodes_button}
    ]
], 'resize_keyboard': True}


# main_user = {'keyboard': [
#     [
#         {'text': templates.button_texts.user_get_stars_button}, 
#         {'text': templates.button_texts.users_get_profile_button},
#     ],
#     [
#         {'text': templates.button_texts.users_get_top_button}, 
#         {'text': templates.button_texts.users_get_gifts_button}, 
#     ],
#     [
#         {'text': templates.button_texts.users_tasks_button}, 
#         {'text': templates.button_texts.users_games_button},
#     ],
#     [
#         {'text': templates.button_texts.users_get_channel_button}, 
#         {'text': templates.button_texts.users_withrawal_stars_button},
#     ],
# ], 'resize_keyboard': True}