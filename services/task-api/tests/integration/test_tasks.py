"""
Task endpointlerinin integration testleri.

Bu testler:
-Task CRUD islemleri
-Authorization (sadece kendi tasklarina erisim)
denetlemektedir.
"""

from httpx import AsyncClient


class TestCreateTask:
    """POST /api/v1/tasks testleri"""

    async def test_create_task_success(self, client: AsyncClient, auth_headers):
        """Authenticated user task olusturabiliyor mu"""
        task_data = {
            "title": "Test Task",
            "description": "Test description",
            "priority": "high",
        }

        response = await client.post(
            "/api/v1/tasks/", json=task_data, headers=auth_headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["title"] == "Test Task"
        assert data["data"]["description"] == "Test description"
        assert data["data"]["priority"] == "high"
        assert (
            data["data"]["status"] == "pending"
        )  # default olarak koyulan deger calisiyo mu kontrol ediyoruz
        assert "id" in data["data"]
        assert "user_id" in data["data"]

    async def test_create_task_without_fails(self, client: AsyncClient, auth_headers):
        """Token olmadan task olusturuyor mu ?"""
        task_data = {"title": "Test Task"}

        response = await client.post("/api/v1/tasks/", json=task_data)

        assert response.status_code == 401

    async def test_create_task_empty_title_fails(
        self, client: AsyncClient, auth_headers
    ):
        """Bos Title ile task olusuyor mu ?"""
        task_data = {"title": "", "description": "test desc"}

        response = await client.post(
            "/api/v1/tasks/", json=task_data, headers=auth_headers
        )

        assert response.status_code == 422


class TestGetTasks:
    """GET /api/v1/tasks task getirme testleridir."""

    async def test_get_all_tasks_empty(self, client: AsyncClient, auth_headers):
        """Hic taski olmayan kullaniciyi getiriyor mu ?"""
        response = await client.get("/api/v1/tasks/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["data"] == []

    async def test_get_all_tasks_returns_own_tasks(
        self, client: AsyncClient, auth_headers
    ):
        """Kullanici task olusturup listeleyebiliyor mu ?"""
        task_data = {
            "title": "Test title",
            "description": "Test description",
            "priority": "high",
        }

        await client.post(
            "/api/v1/tasks/", json={"title": "My Task 1"}, headers=auth_headers
        )

        await client.post(
            "/api/v1/tasks/", json={"title": "My Task 2"}, headers=auth_headers
        )

        response = await client.get("/api/v1/tasks/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        titles = [task["title"] for task in data["data"]]
        assert "My Task 1" in titles
        assert "My Task 2" in titles


class TestGetTaskById:
    """GET /api/v1/tasks{task_id} ile task getirme testleridir."""

    async def test_get_task_by_id_success(self, client: AsyncClient, auth_headers):
        """User kendi taskini id ile getirebiliyor mu"""
        create_response = await client.post(
            "/api/v1/tasks/",
            json={"title": "test title", "description": "test desc"},
            headers=auth_headers,
        )

        task_id = create_response.json()["data"]["id"]

        response = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)

        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["title"] == "test title"

    async def test_get_nonexistent_task_fails(self, client: AsyncClient, auth_headers):
        """Olmayan task icin 404 donuyor mu ?"""
        response = await client.get("/api/v1/tasks/1234", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "TASK_NOT_FOUND"


class TestUpdateTask:
    """PUT /api/v1/tasks/{id} testleri"""

    async def test_update_task_success(self, client: AsyncClient, auth_headers):
        """User kendi Taskini guncelleyebiliyor mu ?"""
        # task olusturuyoruz.
        create_response = await client.post(
            "/api/v1/tasks/", json={"title": "New Task"}, headers=auth_headers
        )

        task_id = create_response.json()["data"]["id"]

        response = await client.put(
            f"/api/v1/tasks/{task_id}",
            json={"title": "updated Task", "description": "updated desc"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["title"] == "updated Task"
        assert data["data"]["description"] == "updated desc"

    async def test_update_nonexistent_task_fails(
        self, client: AsyncClient, auth_headers
    ):
        """Var olmayan task update edilebiliyor mu ?"""
        response = await client.put(
            "/api/v1/tasks/91",
            json={"title": "updated Task", "description": "updated desc"},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestDeleteTask:
    """DELETE /api/v1/tasks/{id} testleri"""

    async def test_delete_task_success(self, client: AsyncClient, auth_headers):
        """User kendi taskini basariyla silebiliyor mu ?"""
        create_response = await client.post(
            "/api/v1/tasks/", json={"title": "pls delete me"}, headers=auth_headers
        )

        task_id = create_response.json()["data"]["id"]

        response = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)

        assert response.status_code == 204

        # silindikten sonra bulunamamasi gerekir
        get_response = await client.get(
            f"/api/v1/tasks/{task_id}", headers=auth_headers
        )

        assert get_response.status_code == 404

    async def test_delete_nonexist_task_fails(self, client: AsyncClient, auth_headers):
        """Olmayan bir task silinmeye calisildiginda noluyor ?"""
        response = await client.delete("/api/v1/tasks/123123", headers=auth_headers)

        assert response.status_code == 404


class TestTaskAuthorization:
    """Task ownership/authorization testleri"""

    async def test_cannot_access_other_users_task(
        self, client: AsyncClient, auth_headers
    ):
        """bir kullanici baska kullanicinin task'ina erisilebiliyor mu ?"""
        create_response = await client.post(
            "/api/v1/tasks/", json={"title": "New Task"}, headers=auth_headers
        )

        task_id = create_response.json()["data"]["id"]

        # ikinci kullanici olusturalim

        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "password": "otherpassword123",
                "full_name": "Other User",
            },
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "other@example.com",
                "password": "otherpassword123",
                "full_name": "Other User",
            },
        )
        other_token = login_response.json()["data"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # ikinci kullanici ilk kullanicinin taskina erismeye calisir.
        response = await client.get(f"/api/v1/tasks/{task_id}", headers=other_headers)

        assert response.status_code == 404

    async def test_cannot_update_other_users_task(
        self, client: AsyncClient, auth_headers
    ):
        """Bir kullanici baska bir kullanicinin taskini guncelleyebiliyor mu ?"""
        create_response = await client.post(
            "/api/v1/tasks/",
            json={"title": "New Task", "description": "New desc"},
            headers=auth_headers,
        )

        # ikinci bir kullanici olusturmaliyiz
        task_id = create_response.json()["data"]["id"]

        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "password": "otherpassword123",
                "full_name": "other user",
            },
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "other@example.com",
                "password": "otherpassword123",
                "full_name": "other user",
            },
        )
        other_token = login_response.json()["data"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        response = await client.put(
            f"/api/v1/tasks/{task_id}",
            json={"title": "Hacked !"},
            headers=other_headers,
        )

        assert response.status_code == 404

    async def test_cannot_delete_other_users_task(
        self, client: AsyncClient, auth_headers
    ):
        """Bir kullanici baska kullanicinin tasklarini silebiliyor mu ?"""
        create_response = await client.post(
            "/api/v1/tasks/", json={"title": "New Task"}, headers=auth_headers
        )

        task_id = create_response.json()["data"]["id"]

        # ikinci kullaniciyi olusturuyoruz.
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": "hacker@example.com",
                "password": "hackerpassword123",
                "full_name": "Hacker ahmet",
            },
        )
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "hacker@example.com",
                "password": "hackerpassword123",
                "full_name": "Hacker ahmet",
            },
        )
        hacker_token = login_response.json()["data"]["access_token"]
        hacker_headers = {"Authorization": f"Bearer {hacker_token}"}

        response = await client.delete(
            f"/api/v1/tasks/{task_id}", headers=hacker_headers
        )

        assert response.status_code == 404

        # Task hala mevcutmu kontrol edelim

        get_response = await client.get(
            f"/api/v1/tasks/{task_id}", headers=auth_headers
        )

        assert get_response.status_code == 200
