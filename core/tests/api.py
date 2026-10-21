import json

from django.urls import reverse
import mock
from rest_framework import status
from rest_framework.test import APITestCase

from taggit.models import Tag

from .helpers import create_image, create_user, create_pin
from core.models import Pin, Image, Board


def _teardown_models():
    Pin.objects.all().delete()
    Image.objects.all().delete()
    Tag.objects.all().delete()
    Board.objects.all().delete()


def mock_requests_get(url, **kwargs):
    response = mock.Mock(content=open('docs/src/imgs/logo-dark.png', 'rb').read())
    return response


def mock_requests_get_with_non_image_content(url, **kwargs):
    response = mock.Mock(content=b"abcd")
    return response


class ImageTests(APITestCase):
    def test_post_create_unsupported(self):
        url = reverse("image-list")
        data = {}
        response = self.client.post(
            url,
            data=data,
            format='json',
        )
        self.assertEqual(response.status_code, 401, response.data)


class BoardPrivacyTests(APITestCase):

    def setUp(self):
        super(BoardPrivacyTests, self).setUp()
        self.owner = create_user("default")
        self.non_owner = create_user("non_owner")

        self.private_board = Board.objects.create(
            name="test_board",
            submitter=self.owner,
            private=True,
        )
        self.board_url = reverse("board-detail", kwargs={"pk": self.private_board.pk})
        self.boards_url = reverse("board-list")

    def tearDown(self):
        _teardown_models()

    def _create_pin_with_non_owner(self, private):
        image = create_image()
        pin = create_pin(self.non_owner, image=image, tags=[])
        pin.private = private
        pin.save()
        return pin

    def test_should_non_owner_and_anonymous_user_has_no_permission_to_list_private_board(self):
        resp = self.client.get(self.boards_url)
        self.assertEqual(len(resp.json()), 0, resp.json())

        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.boards_url)
        self.assertEqual(len(resp.json()), 0, resp.content)

    def test_should_owner_has_permission_to_list_private_board(self):
        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.boards_url)
        self.assertEqual(len(resp.json()), 0, resp.content)

    def test_should_non_owner_and_anonymous_user_has_no_permission_to_view_private_board(self):
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 404)

        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 404)

    def test_should_owner_has_permission_to_view_private_board(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)

    def test_should_owner_has_no_permission_to_add_private_pin_of_other_user_to_board(self):
        self.client.login(username=self.owner.username, password='password')

        private_pin_of_other_user = self._create_pin_with_non_owner(True)

        resp = self.client.patch(self.board_url, data={"pins_to_add": [private_pin_of_other_user.id, ]})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 0, resp.json())

    def test_should_owner_has_permission_to_add_non_private_pin_of_other_user_to_board(self):
        self.client.login(username=self.owner.username, password='password')

        private_pin_of_other_user = self._create_pin_with_non_owner(False)

        resp = self.client.patch(self.board_url, data={"pins_to_add": [private_pin_of_other_user.id, ]})
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(self.board_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_pins'], 1, resp.json())


class PinPrivacyTests(APITestCase):

    def setUp(self):
        super(PinPrivacyTests, self).setUp()
        self.owner = create_user("default")
        self.non_owner = create_user("non_owner")

        with mock.patch('requests.get', mock_requests_get):
            image = create_image()
        self.private_pin = Pin.objects.create(
            submitter=self.owner,
            image=image,
            private=True,
        )
        self.private_pin_url = reverse("pin-detail", kwargs={"pk": self.private_pin.pk})

        self.board = Board.objects.create(name="test_board", submitter=self.owner)
        self.board.pins.add(self.private_pin)
        self.board.save()
        self.board_url = reverse("board-detail", kwargs={"pk": self.board.pk})

    def tearDown(self):
        _teardown_models()

    def test_should_non_owner_and_anonymous_user_has_no_permission_to_list_private_pin(self):
        resp = self.client.get(reverse("pin-list"))
        self.assertEqual(len(resp.json()['results']), 0, resp.content)

        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(reverse("pin-list"))
        self.assertEqual(len(resp.json()['results']), 0, resp.content)

    def test_should_owner_user_has_permission_to_list_private_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(reverse("pin-list"))
        self.assertEqual(len(resp.json()['results']), 1, resp.content)

    def test_should_owner_has_permission_to_view_private_pin(self):
        self.client.login(username=self.owner.username, password='password')
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.private_pin.id)

    def test_should_anonymous_user_has_no_permission_to_view_private_pin(self):
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 404)

    def test_should_non_owner_has_no_permission_to_view_private_pin(self):
        self.client.login(username=self.non_owner.username, password='password')
        resp = self.client.get(self.private_pin_url)
        self.assertEqual(resp.status_code, 404)


class PinTagsFilterTests(APITestCase):

    def setUp(self):
        super(PinTagsFilterTests, self).setUp()
        self.owner = create_user("default")
        with mock.patch('requests.get', mock_requests_get):
            image = create_image()
        self.pin_a = create_pin(self.owner, image, ["a"])
        self.pin_ab = create_pin(self.owner, image, ["a", "b"])
        self.pin_abc = create_pin(self.owner, image, ["a", "b", "c"])
        self.pin_c = create_pin(self.owner, image, ["c"])
        self.private_pin_ab = create_pin(self.owner, image, ["a", "b"])
        self.private_pin_ab.private = True
        self.private_pin_ab.save()

    def tearDown(self):
        _teardown_models()

    def _get_ids(self, query):
        resp = self.client.get(reverse("pin-list") + query)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data['count'], len(data['results']), resp.content)
        return sorted(pin['id'] for pin in data['results'])

    def test_should_match_all_tags_by_default(self):
        ids = self._get_ids("?tags=a&tags=b")
        self.assertEqual(ids, sorted([self.pin_ab.id, self.pin_abc.id]))
        self.assertEqual(self._get_ids("?tags=a&tags=b&tags_mode=all"), ids)

    def test_should_match_any_tag_without_duplicates(self):
        ids = self._get_ids("?tags=b&tags=c&tags_mode=any")
        self.assertEqual(ids, sorted([self.pin_ab.id, self.pin_abc.id, self.pin_c.id]))

    def test_should_return_all_pins_when_no_tag_given(self):
        all_ids = self._get_ids("")
        self.assertEqual(len(all_ids), 4)
        self.assertEqual(self._get_ids("?tags="), all_ids)
        self.assertEqual(self._get_ids("?tags_mode=any"), all_ids)

    def test_should_return_nothing_for_unknown_tag(self):
        self.assertEqual(self._get_ids("?tags=a&tags=unknown"), [])

    def test_should_reject_unknown_mode(self):
        resp = self.client.get(reverse("pin-list") + "?tags=a&tags_mode=some")
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_should_hide_private_pins_from_others_in_both_modes(self):
        for mode in ("all", "any"):
            ids = self._get_ids("?tags=a&tags=b&tags_mode=%s" % mode)
            self.assertNotIn(self.private_pin_ab.id, ids)

    def test_should_show_private_pins_to_owner(self):
        self.client.login(username=self.owner.username, password='password')
        for mode in ("all", "any"):
            ids = self._get_ids("?tags=a&tags=b&tags_mode=%s" % mode)
            self.assertIn(self.private_pin_ab.id, ids)


class PinTests(APITestCase):
    _JSON_TYPE = "application/json"

    def setUp(self):
        super(PinTests, self).setUp()
        self.user = create_user("default")
        self.client.login(username=self.user.username, password='password')

    def tearDown(self):
        _teardown_models()

    @mock.patch('requests.get', mock_requests_get_with_non_image_content)
    def test_should_not_create_pin_if_url_content_invalid(self):
        url = 'http://testserver.com/mocked/logo-01.png'
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'url': url,
            'private': False,
            'referer': referer,
            'description': 'That\'s an Apple!'
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('requests.get', mock_requests_get)
    def test_should_create_pin(self):
        url = 'http://testserver.com/mocked/logo-01.png'
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'url': url,
            'private': False,
            'referer': referer,
            'description': 'That\'s an Apple!'
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pin = Pin.objects.get(url=url)
        self.assertIsNotNone(pin.image.image)

    @mock.patch('requests.get', mock_requests_get)
    def test_post_create_url_with_empty_tags(self):
        url = 'http://testserver.com/mocked/logo-02.png'
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'url': url,
            'referer': referer,
            'description': 'That\'s an Apple!',
            'tags': []
        }
        response = self.client.post(create_url, data=post_data, format="json")
        self.assertEqual(
            response.status_code, status.HTTP_201_CREATED, response.json()
        )
        self.assertEqual(Image.objects.count(), 1)
        pin = Pin.objects.get(url=url)
        self.assertIsNotNone(pin.image.image)
        self.assertEqual(pin.tags.count(), 0)

    def test_should_post_create_pin_with_existed_image(self):
        image = create_image()
        create_pin(self.user, image=image, tags=[])
        create_url = reverse("pin-list")
        referer = 'http://testserver.com/'
        post_data = {
            'referer': referer,
            'image_by_id': image.pk,
            'description': 'That\'s something else (probably a CC logo)!',
            'tags': ['random', 'tags'],
        }
        response = self.client.post(create_url, data=post_data, format="json")
        resp_data = response.json()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, resp_data)
        self.assertEqual(
            resp_data['description'],
            'That\'s something else (probably a CC logo)!',
            resp_data
        )
        self.assertEquals(Pin.objects.count(), 2)

    def _post_pin_with_image(self, image_pk):
        return self.client.post(
            reverse("pin-list"), {'image_by_id': image_pk}, format="json",
        )

    def test_should_share_image_of_visible_pin(self):
        image = create_image()
        create_pin(create_user("other"), image, [])
        response = self._post_pin_with_image(image.pk)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())
        self.assertEqual(Image.objects.count(), 1)
        self.assertEqual(Pin.objects.get(pk=response.json()['id']).image_id, image.pk)

    def test_should_reject_image_of_others_private_pin(self):
        image = create_image()
        pin = create_pin(create_user("other"), image, [])
        pin.private = True
        pin.save()
        response = self._post_pin_with_image(image.pk)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Pin.objects.count(), 1)
        # Same error as for an image that doesn't exist, so it isn't revealed
        missing = self._post_pin_with_image(image.pk + 1000).json()['image_by_id']
        self.assertEqual(
            response.json()['image_by_id'],
            [m.replace(str(image.pk + 1000), str(image.pk)) for m in missing],
        )

    def test_owner_should_reuse_own_private_image(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        pin.private = True
        pin.save()
        response = self._post_pin_with_image(image.pk)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.json())

    def _image_files(self, image):
        return [image.image] + [t.image for t in image.thumbnail_set.all()]

    def test_delete_pin_should_keep_shared_image(self):
        image = create_image()
        other_pin = create_pin(create_user("other"), image, [])
        pin = create_pin(self.user, image, [])
        files = self._image_files(image)
        self.client.delete(reverse("pin-detail", kwargs={"pk": pin.pk}))
        self.assertFalse(Pin.objects.filter(pk=pin.pk).exists())
        self.assertTrue(Pin.objects.filter(pk=other_pin.pk).exists())
        self.assertTrue(Image.objects.filter(pk=image.pk).exists())
        for f in files:
            self.assertTrue(f.storage.exists(f.name), f.name)

    def test_delete_last_pin_should_remove_image(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        files = self._image_files(image)
        self.client.delete(reverse("pin-detail", kwargs={"pk": pin.pk}))
        self.assertFalse(Image.objects.filter(pk=image.pk).exists())
        for f in files:
            self.assertFalse(f.storage.exists(f.name), f.name)

    def test_patch_detail_unauthenticated(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        self.client.logout()
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        response = self.client.patch(uri, format='json', data={})
        self.assertEqual(response.status_code, 401, response.data)

    def test_patch_detail(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        new = {'description': 'Updated description'}

        response = self.client.patch(
            uri, new, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        self.assertEqual(Pin.objects.count(), 1)
        self.assertEqual(Pin.objects.get(pk=pin.pk).description, new['description'])

    def test_delete_detail_unauthenticated(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        self.client.logout()
        resp = self.client.delete(uri)
        self.assertEqual(resp.status_code, 401, resp.data)

    def test_delete_detail(self):
        image = create_image()
        pin = create_pin(self.user, image, [])
        uri = reverse("pin-detail", kwargs={"pk": pin.pk})
        self.client.delete(uri)
        self.assertEqual(Pin.objects.count(), 0)
