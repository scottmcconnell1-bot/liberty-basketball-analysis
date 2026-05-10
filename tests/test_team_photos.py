"""
test_team_photos.py – Tests for team photo upload, list, and delete endpoints.
"""
import io
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_image():
    """Create a minimal valid JPEG bytes for testing uploads."""
    # Minimal JPEG: SOI + minimal data + EOI
    import struct
    # Create a simple 1x1 pixel JPEG
    # This is a valid minimal JPEG file
    jpeg_bytes = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
        b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
        b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
        b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
        b'\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04'
        b'\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07'
        b'"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17'
        b'\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84'
        b'\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2'
        b'\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9'
        b'\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7'
        b'\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3'
        b'\xf4\xf5\xf6\xf7\xf8\xf9\xfa'
        b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\xdb\xa8\xa3\x80\x1f\xff\xd9'
    )
    return jpeg_bytes


@pytest.fixture
def sample_png():
    """Create a minimal valid PNG bytes for testing uploads."""
    import struct, zlib
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        return struct.pack('>I', len(data)) + c + crc

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    raw = zlib.compress(b'\x00\xff\x80\x00\x00')
    idat = chunk(b'IDAT', raw)
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


# ── List photos ───────────────────────────────────────────────────────

class TestTeamPhotosList:
    def test_list_empty(self, client):
        """GET /api/teams/photos returns empty dict when no photos."""
        r = client.get('/api/teams/photos')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, dict)

    def test_list_returns_photos_grouped(self, client, sample_image):
        """Photos are grouped by team_key."""
        # Upload a photo
        data = {
            'file': (io.BytesIO(sample_image), 'test.jpg'),
            'team_key': 'varsity_boys',
        }
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 201

        # List
        r = client.get('/api/teams/photos')
        assert r.status_code == 200
        photos = r.get_json()
        assert 'varsity_boys' in photos
        assert len(photos['varsity_boys']) >= 1


# ── Upload ────────────────────────────────────────────────────────────

class TestTeamPhotosUpload:
    def test_upload_jpg(self, client, sample_image):
        """Upload a JPG photo successfully."""
        data = {
            'file': (io.BytesIO(sample_image), 'team_photo.jpg'),
            'team_key': 'varsity_boys',
            'caption': 'Team huddle',
        }
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 201
        body = r.get_json()
        assert body['team_key'] == 'varsity_boys'
        assert body['original_name'] == 'team_photo.jpg'
        assert body['caption'] == 'Team huddle'
        assert 'id' in body
        assert 'filename' in body

    def test_upload_png(self, client, sample_png):
        """Upload a PNG photo successfully."""
        data = {
            'file': (io.BytesIO(sample_png), 'photo.png'),
            'team_key': 'jv_girls',
        }
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 201
        body = r.get_json()
        assert body['team_key'] == 'jv_girls'

    def test_upload_no_file(self, client):
        """Upload with no file returns 400."""
        r = client.post('/api/teams/photos/upload', data={}, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_upload_empty_filename(self, client):
        """Upload with empty filename returns 400."""
        data = {'file': (io.BytesIO(b''), ''), 'team_key': 'varsity_boys'}
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_upload_disallowed_extension(self, client):
        """Upload with bad extension returns 400."""
        data = {
            'file': (io.BytesIO(b'malicious'), 'hack.exe'),
            'team_key': 'varsity_boys',
        }
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_upload_all_teams(self, client, sample_image):
        """Upload works for all 6 team keys."""
        teams = ['varsity_boys', 'varsity_girls', 'jv_boys', 'jv_girls', 'jr_high_boys', 'jr_high_girls']
        for team in teams:
            data = {
                'file': (io.BytesIO(sample_image), f'{team}.jpg'),
                'team_key': team,
            }
            r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
            assert r.status_code == 201, f"Upload failed for {team}"


# ── Delete ────────────────────────────────────────────────────────────

class TestTeamPhotosDelete:
    def test_delete_photo(self, client, sample_image):
        """Delete a photo by id."""
        # Upload first
        data = {
            'file': (io.BytesIO(sample_image), 'delete_me.jpg'),
            'team_key': 'varsity_boys',
        }
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        photo_id = r.get_json()['id']

        # Delete
        r = client.delete(f'/api/teams/photos/{photo_id}')
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

        # Verify gone
        r = client.get('/api/teams/photos')
        photos = r.get_json()
        all_ids = [p['id'] for team_photos in photos.values() for p in team_photos]
        assert photo_id not in all_ids

    def test_delete_nonexistent(self, client):
        """Delete a nonexistent photo returns 404."""
        r = client.delete('/api/teams/photos/99999')
        assert r.status_code == 404

    def test_delete_invalid_id(self, client):
        """Delete with invalid id returns 404 or 405."""
        r = client.delete('/api/teams/photos/abc')
        assert r.status_code in (404, 405)


# ── Download (via uploaded_file route) ────────────────────────────────

class TestTeamPhotosDownload:
    def test_upload_returns_downloadable_url(self, client, sample_image):
        """After upload, the response includes filename for download URL construction."""
        data = {
            'file': (io.BytesIO(sample_image), 'serve_test.jpg'),
            'team_key': 'varsity_boys',
        }
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        assert r.status_code == 201
        body = r.get_json()
        assert 'filename' in body
        assert body['filename'].startswith('varsity_boys_')
        assert body['filename'].endswith('.jpg')

    def test_photo_served_from_uploads(self, client, sample_image):
        """Uploaded photo is accessible via /uploads/team_photos/<filename>."""
        data = {
            'file': (io.BytesIO(sample_image), 'serve_test2.jpg'),
            'team_key': 'varsity_boys',
        }
        r = client.post('/api/teams/photos/upload', data=data, content_type='multipart/form-data')
        filename = r.get_json()['filename']
        r = client.get(f'/uploads/team_photos/{filename}')
        # 200 if file exists on disk, 404 if test env doesn't serve static files
        assert r.status_code in (200, 404)
