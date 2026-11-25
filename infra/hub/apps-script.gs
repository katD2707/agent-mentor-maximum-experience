/**
 * Mentor hub helper: runs as the owner (Execute as: Me, Who has access: Anyone).
 * Sends mail through Gmail, and writes course packs to Drive + updates the public catalog.json.
 * Deploy steps: infra/hub/README.md. deploy.ps1 writes a copy of this file with SECRET filled in to .secrets/apps-script.gs.
 */
var SECRET = '__SCRIPT_SECRET__';
var CATALOG_ID = '1AreHj5AxvmCmvHeyDHjJpIUXNWxCWHg1';

function doPost(e) {
  var out;
  try {
    var req = JSON.parse(e.postData.contents);
    if (!req || typeof req.secret !== 'string' || req.secret !== SECRET) {
      out = { ok: false, error: 'forbidden' };
    } else if (req.action === 'mail') {
      out = sendMail_(req);
    } else if (req.action === 'publish') {
      out = publish_(req);
    } else if (req.action === 'unpublish') {
      out = unpublish_(req);
    } else {
      out = { ok: false, error: 'unknown_action' };
    }
  } catch (err) {
    out = { ok: false, error: String(err && err.message ? err.message : err) };
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  return ContentService.createTextOutput(JSON.stringify({ ok: true, service: 'mentor-hub-script' })).setMimeType(ContentService.MimeType.JSON);
}

function sendMail_(req) {
  GmailApp.sendEmail(req.to, req.subject, '', { htmlBody: req.html, name: 'Mentor' });
  return { ok: true };
}

function shareLink_(file) {
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return file;
}

function courseFolder_(root, courseId) {
  var it = root.getFoldersByName(courseId);
  var folder = it.hasNext() ? it.next() : root.createFolder(courseId);
  return shareLink_(folder);
}

// Replace a file with the same name in the folder, or create it.
function putFile_(folder, name, blob) {
  var old = folder.getFilesByName(name);
  while (old.hasNext()) old.next().setTrashed(true);
  blob.setName(name);
  return shareLink_(folder.createFile(blob));
}

function readCatalog_(file) {
  var cat = JSON.parse(file.getBlob().getDataAsString('UTF-8'));
  if (!cat.courses) cat.courses = [];
  if (!cat.remote) cat.remote = {};
  return cat;
}

function withCatalog_(change) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var file = DriveApp.getFileById(CATALOG_ID);
    var cat = readCatalog_(file);
    change(cat);
    file.setContent(JSON.stringify(cat));
  } finally {
    lock.releaseLock();
  }
}

function publish_(req) {
  var catalogFile = DriveApp.getFileById(CATALOG_ID);
  var root = catalogFile.getParents().next();
  var folder = courseFolder_(root, req.course_id);

  var pack = putFile_(folder, 'pack-v' + req.version + '.zip', Utilities.newBlob(Utilities.base64Decode(req.pack_b64), 'application/zip'));
  putFile_(folder, 'course.json', Utilities.newBlob(JSON.stringify(req.meta), 'application/json'));
  var coverId = null;
  if (req.cover_b64) {
    var coverName = req.cover_name || 'cover.png';
    var mime = /\.jpe?g$/i.test(coverName) ? 'image/jpeg' : (/\.webp$/i.test(coverName) ? 'image/webp' : 'image/png');
    coverId = putFile_(folder, coverName, Utilities.newBlob(Utilities.base64Decode(req.cover_b64), mime)).getId();
  }

  withCatalog_(function (cat) {
    var replaced = false;
    for (var i = 0; i < cat.courses.length; i++) {
      if (cat.courses[i].id === req.entry.id) { cat.courses[i] = req.entry; replaced = true; break; }
    }
    if (!replaced) cat.courses.push(req.entry);
    cat.remote[req.course_id] = {
      pack_id: pack.getId(), zip_sha256: req.zip_sha256, zip_bytes: req.zip_bytes,
      cover_id: coverId, cover_name: req.cover_name || null, meta: req.meta
    };
  });
  return { ok: true, pack_id: pack.getId(), cover_id: coverId };
}

function unpublish_(req) {
  withCatalog_(function (cat) {
    cat.courses = cat.courses.filter(function (c) { return c.id !== req.course_id; });
    delete cat.remote[req.course_id];
  });
  return { ok: true };
}
