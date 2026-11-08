from app.core.events import domain_event_publisher
from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.core.logging import get_logger
from app.db.entities import BoardEntity, BoardListEntity, LabelEntity
from app.db.entities.board import BoardPrivacy
from app.db.unit_of_work import TaskUnitOfWork
from app.models.board import (
    BoardCreate,
    BoardDetail,
    BoardResponse,
    BoardUpdate,
    BoardWithCounts,
    LabelCreate,
    LabelResponse,
    LabelUpdate,
    ListCreate,
    ListResponse,
    ListUpdate,
    is_local_model,
)
from app.services.activity import ActivityLogger, diff
from app.services.ordering import STEP, place_at
from app.services.palette import next_free_color

logger = get_logger(__name__)

DEFAULT_LISTS: list[tuple[str, bool]] = [
    ("Yapılacak", False),
    ("Yapılıyor", False),
    ("Tamamlandı", True),
]
DEFAULT_BOARD_NAME = "Genel"
INBOX_KIND = "inbox"
INBOX_BOARD_NAME = "Gelen Kutusu"
INBOX_LIST_NAME = "Gelen"


class BoardService:
    """Board, liste ve etiket islemleri."""

    def __init__(self, uow: TaskUnitOfWork):
        self.uow = uow
        self.activity = ActivityLogger(uow)

    # ---------------- yardimcilar ----------------
    async def get_owned_board(self, board_id: int, user_id: int) -> BoardEntity:
        board = await self.uow.boards.get_owned(board_id, user_id)
        if board is None:
            raise NotFoundException("Board", board_id)
        return board

    async def get_owned_list(self, list_id: int, user_id: int) -> BoardListEntity:
        lst = await self.uow.lists.get_owned(list_id, user_id)
        if lst is None:
            raise NotFoundException("List", list_id)
        return lst

    async def _create_board_entity(
        self, user_id: int, data: BoardCreate
    ) -> tuple[BoardEntity, list[BoardListEntity]]:
        position = await self.uow.boards.max_position(user_id) + STEP
        board = BoardEntity(
            user_id=user_id,
            position=position,
            **data.model_dump(exclude={"lists"}),
        )
        await self.uow.boards.create(board)
        await self.uow.flush()

        specs = [(name, False) for name in data.lists] if data.lists else DEFAULT_LISTS
        lists = []
        for i, (name, is_done) in enumerate(specs, start=1):
            lst = BoardListEntity(
                user_id=user_id,
                board_id=board.id,
                name=name,
                position=i * STEP,
                is_done_list=is_done,
            )
            await self.uow.lists.create(lst)
            lists.append(lst)
        await self.uow.flush()
        await self.activity.log(
            user_id,
            "board",
            board.id,
            "created",
            board_id=board.id,
            changes={"name": board.name},
        )
        return board, lists

    async def get_or_create_default(
        self, user_id: int
    ) -> tuple[BoardEntity, BoardListEntity]:
        """
        Board'u belirtilmeden olusturulan kartlar (eski /tasks API'si) icin
        varsayilan 'Genel' board'u ve ilk listesini doner. Commit etmez.
        """
        board = await self.uow.boards.find_by_name(user_id, DEFAULT_BOARD_NAME)
        if board is not None:
            lists = await self.uow.lists.list_for_board(board.id)
            if lists:
                return board, lists[0]
            lst = BoardListEntity(
                user_id=user_id, board_id=board.id, name="Yapılacak", position=STEP
            )
            await self.uow.lists.create(lst)
            await self.uow.flush()
            return board, lst
        board, lists = await self._create_board_entity(
            user_id, BoardCreate(name=DEFAULT_BOARD_NAME)
        )
        return board, lists[0]

    async def get_or_create_inbox(
        self, user_id: int
    ) -> tuple[BoardEntity, BoardListEntity]:
        """
        Entegrasyonlardan gelen islerin dustugu "Gelen Kutusu" board'u ve tek
        listesi. Gizlilik varsayilani local_only. Commit etmez.
        """
        board = await self.uow.boards.find_inbox(user_id)
        if board is not None:
            lists = await self.uow.lists.list_for_board(board.id)
            if lists:
                return board, lists[0]
            lst = BoardListEntity(
                user_id=user_id, board_id=board.id, name=INBOX_LIST_NAME, position=STEP
            )
            await self.uow.lists.create(lst)
            await self.uow.flush()
            return board, lst
        board, lists = await self._create_board_entity(
            user_id,
            BoardCreate(
                name=INBOX_BOARD_NAME,
                privacy=BoardPrivacy.LOCAL_ONLY,
                color="#6366f1",
                icon="inbox",
                scope_description=(
                    "Dış kaynaklardan (Trello, Microsoft To Do…) gelen, henüz "
                    "bir alana yerleştirilmemiş işler."
                ),
                lists=[INBOX_LIST_NAME],
            ),
        )
        board.system_kind = INBOX_KIND
        await self.uow.flush()
        return board, lists[0]

    # ---------------- board ----------------
    async def list_boards(
        self, user_id: int, include_archived: bool = False
    ) -> list[BoardWithCounts]:
        boards = await self.uow.boards.list_for_user(user_id, include_archived)
        counts = await self.uow.boards.open_card_counts(user_id)
        return [
            BoardWithCounts(
                **BoardResponse.model_validate(b).model_dump(),
                open_card_count=counts.get(b.id, 0),
            )
            for b in boards
        ]

    async def create_board(self, user_id: int, data: BoardCreate) -> BoardResponse:
        _check_model_privacy(data.privacy, data.default_model_id)
        board, _ = await self._create_board_entity(user_id, data)
        await self.uow.commit()
        await domain_event_publisher.publish(
            "board.created",
            {"board_id": board.id, "user_id": user_id, "name": board.name},
        )
        return BoardResponse.model_validate(board)

    async def get_detail(self, board_id: int, user_id: int) -> BoardDetail:
        # Dongusel importu onlemek icin burada
        from app.services.card import CardService

        board = await self.get_owned_board(board_id, user_id)
        lists = await self.uow.lists.list_for_board(board.id)
        labels = await self.uow.labels.list_for_board(board.id)
        cards = await self.uow.tasks.list_for_board(board.id)
        summaries = await CardService(self.uow).summaries(cards)
        return BoardDetail(
            board=BoardResponse.model_validate(board),
            lists=[ListResponse.model_validate(lst) for lst in lists],
            cards=summaries,
            labels=[LabelResponse.model_validate(lb) for lb in labels],
        )

    async def update_board(
        self, board_id: int, user_id: int, data: BoardUpdate
    ) -> BoardResponse:
        board = await self.get_owned_board(board_id, user_id)
        update = data.model_dump(exclude_unset=True)
        privacy = update.get("privacy", board.privacy)
        if "default_model_id" in update:
            _check_model_privacy(privacy, update["default_model_id"])
        elif not is_local_model(board.default_model_id) and privacy == (
            BoardPrivacy.LOCAL_ONLY
        ):
            # Board "sadece local"e cekildi: bulut varsayilani birakilamaz
            update["default_model_id"] = None
        changes = diff(board, update)
        for key, value in update.items():
            setattr(board, key, value)
        if changes:
            action = (
                "archived" if changes.get("is_archived", [None, None])[1] else "updated"
            )
            await self.activity.log(
                user_id, "board", board.id, action, board_id=board.id, changes=changes
            )
        await self.uow.commit()
        return BoardResponse.model_validate(board)

    async def delete_board(self, board_id: int, user_id: int) -> None:
        board = await self.get_owned_board(board_id, user_id)
        if board.system_kind == INBOX_KIND:
            raise ConflictException(
                "INBOX_PROTECTED", "Gelen Kutusu silinemez; yeniden adlandırabilirsiniz."
            )
        await self.activity.log(
            user_id,
            "board",
            board.id,
            "deleted",
            board_id=board.id,
            changes={"name": board.name},
        )
        await self.uow.day_plan_items.detach_board(board.id)
        from app.services.goal import detach_goals

        await detach_goals(self.uow.session, board_id=board.id)
        await self.uow.events.delete_for_board(board.id)
        await self.uow.time_sessions.detach_board_cards(board.id)
        await self.uow.boards.delete_cascade(board)
        await self.uow.commit()

    # ---------------- liste ----------------
    async def create_list(
        self, board_id: int, user_id: int, data: ListCreate
    ) -> ListResponse:
        board = await self.get_owned_board(board_id, user_id)
        lists = await self.uow.lists.list_for_board(board.id)
        position = (lists[-1].position if lists else 0) + STEP
        lst = BoardListEntity(
            user_id=user_id, board_id=board.id, position=position, **data.model_dump()
        )
        await self.uow.lists.create(lst)
        await self.uow.flush()
        await self.activity.log(
            user_id,
            "list",
            lst.id,
            "created",
            board_id=board.id,
            changes={"name": lst.name},
        )
        await self.uow.commit()
        return ListResponse.model_validate(lst)

    async def update_list(
        self, list_id: int, user_id: int, data: ListUpdate
    ) -> ListResponse:
        lst = await self.get_owned_list(list_id, user_id)
        update = data.model_dump(exclude_unset=True)
        changes = diff(lst, update)
        for key, value in update.items():
            setattr(lst, key, value)
        if changes:
            await self.activity.log(
                user_id,
                "list",
                lst.id,
                "updated",
                board_id=lst.board_id,
                changes=changes,
            )
        await self.uow.commit()
        return ListResponse.model_validate(lst)

    async def move_list(self, list_id: int, user_id: int, index: int) -> ListResponse:
        lst = await self.get_owned_list(list_id, user_id)
        siblings = [
            item
            for item in await self.uow.lists.list_for_board(lst.board_id)
            if item.id != lst.id
        ]
        place_at(siblings, lst, index)
        await self.uow.commit()
        return ListResponse.model_validate(lst)

    async def delete_list(self, list_id: int, user_id: int) -> None:
        lst = await self.get_owned_list(list_id, user_id)
        if await self.uow.tasks.count_in_list(lst.id) > 0:
            raise ConflictException(
                "LIST_NOT_EMPTY",
                "Liste boş değil. Önce kartları taşıyın ya da arşivleyin.",
            )
        await self.activity.log(
            user_id,
            "list",
            lst.id,
            "deleted",
            board_id=lst.board_id,
            changes={"name": lst.name},
        )
        await self.uow.lists.delete(lst)
        await self.uow.commit()

    # ---------------- etiket ----------------
    async def create_label(
        self, board_id: int, user_id: int, data: LabelCreate
    ) -> LabelResponse:
        board = await self.get_owned_board(board_id, user_id)
        values = data.model_dump()
        if not values.get("color"):
            existing = await self.uow.labels.list_for_board(board.id)
            values["color"] = next_free_color([lb.color for lb in existing])
        label = LabelEntity(user_id=user_id, board_id=board.id, **values)
        await self.uow.labels.create(label)
        await self.uow.commit()
        return LabelResponse.model_validate(label)

    async def update_label(
        self, label_id: int, user_id: int, data: LabelUpdate
    ) -> LabelResponse:
        label = await self.uow.labels.get_owned(label_id, user_id)
        if label is None:
            raise NotFoundException("Label", label_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(label, key, value)
        await self.uow.commit()
        return LabelResponse.model_validate(label)

    async def delete_label(self, label_id: int, user_id: int) -> None:
        label = await self.uow.labels.get_owned(label_id, user_id)
        if label is None:
            raise NotFoundException("Label", label_id)
        await self.uow.card_labels.delete_for_label(label.id)
        await self.uow.labels.delete(label)
        await self.uow.commit()


def _check_model_privacy(privacy: BoardPrivacy, model_id: str | None) -> None:
    if privacy == BoardPrivacy.LOCAL_ONLY and not is_local_model(model_id):
        raise ValidationException(
            "“Sadece local” board'un varsayılan modeli bulut modeli olamaz"
        )
