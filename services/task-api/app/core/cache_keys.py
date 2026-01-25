"""
Cache key'lerini olusturmak icin yardimci fonksiyonlar.

"""

def get_task_list_cache_key(
        user_id : int,
        status : str | None = None,
        priority : str | None = None,
        search : str | None = None,
        page : int = 1
) -> str:
    """
    Docstring for get_task_list_cache_key
    Task listesi cache key'i olusturur
    Format: task:user {user_id};list{status}{priority}{search}{page}
    Ornek: get_task_list_cache_key(1,"pending","high",None,1)
    ->"tasks:user:1:list:pending:high::1"
    """
    # None degerlerini all yapalim ki key de bosluk olmasin
    status_str = status or "all"
    priority_str = priority or "all"
    search_str = search or ""
    
    return f"tasks:user:{user_id}:list:{status_str}:{priority_str}:{search_str}:{page}"

def get_task_detail_cache_key(user_id: int,task_id: int) -> str:
    """
    Docstring for get_task_detail_cache_key
    
    Task detay cache key'i olusturur.
    Format: task:user:{user_id}:detail:{task_id}
    ornek:
    get_task_detail_cache_key(1, 5)
    ->"tasks:user:1:detail:5"
    
    """
    return f"tasks:user:{user_id}:detail:{task_id}"

def get_task_user_pattern(user_id: int)-> str:
    """
    Belirli bir kullanicinin tum task cache'lerini silmek icin pattern.
    Format: tasks:user:{user_id}:*
    Kullanim:
        await cache_delete_pattern(get_task_user_pattern(1))
        ->user:1'in tum cache'leri silinir.'
    """
    return f"tasks:user:{user_id}:*"