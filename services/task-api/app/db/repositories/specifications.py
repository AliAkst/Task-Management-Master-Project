from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from sqlalchemy.sql import Select
from sqlalchemy import select, or_, desc, asc
from app.db.entities.task import TaskEntity, TaskStatus, TaskPriority


#Generic tip tanimi (hangi model ile calisacagimi temsil eder)
T= TypeVar("T")

class Specification(ABC, Generic[T]):
    """Sorgu kriterlerini tanimlayan ana soyut sinif"""

    @abstractmethod
    def apply(self, query: Select) -> Select:
        """Kriterleri SQLAlchemy Select nesnesine uygular."""
        pass

class AndSpecification(Specification[T]):
    """iki farkli kriterleri AND (VE) mantigi ile birlestirir."""

    def __init__(self, spec1: Specification[T], spec2: Specification[T]):
        self.spec1 = spec1
        self.spec2 = spec2

    def apply(self, query: Select) -> Select:
        # Once birinci, sonra ikinci kriteri query'ye zincirleme ekler.
        query = self.spec1.apply(query)
        query = self.spec2.apply(query)
        return query

class TaskStatusSpecification(Specification[TaskEntity]):
    """Görevleri durumlarina göre(Pending vs.)Filtreler"""
    def __init__(self, status: TaskStatus):
        self.status = status
    
    def apply(self, query: Select) -> Select:
        return query.where(TaskEntity.status == self.status)
    
class TaskPrioritySpecification(Specification[TaskEntity]):
    """Görevleri öncelik seviyelerine göre filtreler."""
    def __init__(self, priority: TaskPriority):
        self.priority = priority
        
    def apply(self, query: Select)-> Select:
        return query.where(TaskEntity.priority == self.priority)

class TaskUserSpecification(Specification[TaskEntity]):
    """Belirli bir kullanıcıya ait görevleri filtreler."""
    def __init__(self,user_id: int):
        self.user_id = user_id

    def apply(self, query: Select) -> Select:
        return query.where(TaskEntity.user_id==self.user_id)
    
class TaskSearchSpecification(Specification[TaskEntity]):
    """Başlık veya açıklama içerisinde kelime bazlı arama yapar"""
    def __init__(self,search: str):
        self.search = f"%{search}%"
    
    def apply(self, query: Select)-> Select:
        return query.where(
            or_(
                TaskEntity.title.ilike(self.search),
                TaskEntity.description.ilike(self.search)
            )
        )
class PaginationSpecification(Specification[TaskEntity]):
    """Veritabanı sonuçlarını sayfalara böler(offset ve limit mantığıyla)"""
    def __init__(self,page:int, page_size:int):
        self.page = page
        self.page_size = page_size
    
    def apply(self,query:Select)->Select:
        offset = (self.page -1) * self.page_size
        return query.offset(offset).limit(self.page_size)

class OrderBySpecification(Specification[TaskEntity]):
    """Sonuçları belirli bir kolona göre artan veya azalan şekilde sıralar."""
    def __init__(self, field: str, descending: bool = False):
        self.field = field
        self.descending = descending
    
    def apply(self, query:Select)->Select:
        column = getattr(TaskEntity,self.field,TaskEntity.id)
        order_func = desc if self.descending else asc
        return query.order_by(order_func(column))
    