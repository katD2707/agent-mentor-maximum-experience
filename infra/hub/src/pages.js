// Self-contained HTML pages (inline CSS and JS): the teacher declaration form (/ho-so) and the admin page (/quan-tri).
import { esc } from "./util.js";

const FONT = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Lexend:wght@400;500;600;700;800&display=swap&subset=vietnamese">';
const IC = {
  mail: '<path d="M3 6h18v12H3z"/><path d="m3 7 9 7 9-7"/>',
  chev: '<path d="m6 9 6 6 6-6"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
};
const icon = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n]}</svg>`;

const WARM_CSS = `
*{box-sizing:border-box}
:root{color-scheme:light;--cream:#fff7e6;--edge:#e0c294;--ink:#3a2010;--ink2:#6b4a2e;--brown:#7d4c22;--green:#1b7340;--greend:#165c32;--red:#b3321d;--redsoft:#fde4dc;--focus:#1d4fb8}
body{margin:0;background:#f6ead2;color:var(--ink);font:400 16px/1.5 Lexend,system-ui,sans-serif}
h1{margin:0;line-height:1.2}
svg{display:block;max-width:100%}
[hidden]{display:none!important}
.page{max-width:680px;margin:0 auto;padding:24px 16px 72px}
.brand{display:flex;align-items:center;gap:10px;margin-bottom:20px;font-weight:800;color:var(--brown)}
.mark{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;background:var(--green);color:#fff;font-weight:800;box-shadow:inset 0 -3px 0 rgba(0,0,0,.2)}
.sheet{background:var(--cream);border:2px solid var(--edge);border-radius:16px;padding:clamp(18px,5vw,34px);display:grid;gap:24px;box-shadow:0 4px 0 #e0c294}
.sheet h1{font-size:clamp(1.4em,4vw,1.8em);font-weight:800}
.who{display:inline-flex;align-items:center;gap:8px;margin-top:8px;padding:4px 12px;border-radius:99px;background:#f3dcb0;font-size:.9em;font-weight:600;overflow-wrap:anywhere}
.who svg{width:18px;height:18px;flex:none;color:var(--brown)}
.banner{display:flex;gap:10px;padding:12px 14px;border-radius:12px;background:var(--redsoft);color:#7a1f10;font-weight:600;border:2px solid var(--red)}
.banner svg{flex:none;width:22px;height:22px;margin-top:1px;color:var(--red)}
.banner b{display:block}
fieldset{border:0;margin:0;padding:0;min-width:0;display:grid;gap:8px}
legend,.lbl{padding:0;font-weight:700;font-size:.95em}
.row2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
@media(max-width:560px){.row2{grid-template-columns:minmax(0,1fr)}}
.f{display:grid;gap:6px;align-content:start}
.f input[type=text],.multi summary{min-height:50px;padding:0 14px;border-radius:12px;border:2px solid #d6b27a;background:#fffdf7;width:100%;color:var(--ink);font:inherit}
.f input[type=text]:focus{outline:3px solid var(--focus);border-color:var(--focus)}
.f.bad input[type=text],.bad .multi summary,.bad .chips,.bad .drop2{border-color:var(--red)}
.err{display:none;color:var(--red);font-size:.88em;font-weight:600}
.bad>.err,.bad .err{display:block}
.hint{color:var(--ink2);font-size:.88em}
.multi summary{display:flex;align-items:center;justify-content:space-between;gap:10px;cursor:pointer;list-style:none;font-weight:500}
.multi summary::-webkit-details-marker{display:none}
.multi summary svg{width:18px;height:18px;flex:none;transition:transform .15s}
.multi[open] summary svg{transform:rotate(180deg)}
.multi summary:focus-visible{outline:3px solid var(--focus)}
.ph{color:var(--ink2)}
.panel{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:2px 10px;margin-top:6px;padding:8px;border-radius:12px;border:2px solid #d6b27a;background:#fffdf7}
.multi label{display:flex;align-items:center;gap:10px;min-height:44px;padding:0 8px;border-radius:8px;cursor:pointer}
.multi label:hover{background:#f6e3c2}
.multi input{width:20px;height:20px;accent-color:var(--green);flex:none}
.chips{display:flex;flex-wrap:wrap;gap:8px;border-radius:12px;border:2px solid transparent}
.chip{position:relative}
.chip input{position:absolute;opacity:0;inset:0;width:100%;height:100%;margin:0;cursor:pointer}
.chip span{display:inline-flex;align-items:center;min-height:46px;padding:0 18px;border-radius:99px;border:2px solid #d6b27a;background:#fffdf7;font-weight:600;font-size:.95em}
.chip input:checked+span{background:#ffcf3d;border-color:#c99a10;font-weight:700}
.chip input:focus-visible+span{outline:3px solid var(--focus);outline-offset:2px}
.drop2{display:grid;justify-items:center;gap:6px;padding:22px 16px;text-align:center;border-radius:12px;border:2px dashed #c9a46d;background:#fffdf7;cursor:pointer;position:relative}
.drop2:hover{border-color:var(--brown)}
.drop2:focus-within{outline:3px solid var(--focus);outline-offset:2px}
.drop2 svg{width:28px;height:28px;color:var(--brown)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.shots{display:flex;flex-wrap:wrap;gap:12px}
.shot{position:relative;width:112px;height:84px;border-radius:8px;overflow:hidden;border:2px solid var(--edge);background:#fff}
.shot img{width:100%;height:100%;object-fit:cover}
.shot button{position:absolute;top:4px;right:4px;width:30px;height:30px;border-radius:99px;border:0;background:rgba(58,32,16,.85);color:#fff;display:grid;place-items:center;cursor:pointer}
.shot button svg{width:16px;height:16px}
.pledge{display:flex;gap:12px;align-items:flex-start;padding:14px;border-radius:12px;background:#fffdf7;border:2px solid #d6b27a;cursor:pointer}
.pledge input{width:22px;height:22px;margin:2px 0 0;accent-color:var(--green);flex:none}
.bad.pledge{border-color:var(--red)}
.go{min-width:200px;min-height:56px;padding:0 28px;border-radius:14px;border:0;background:var(--green);color:#fff;font:inherit;font-size:1.1em;font-weight:800;cursor:pointer;box-shadow:0 5px 0 var(--greend)}
.go:active{transform:translateY(3px);box-shadow:0 2px 0 var(--greend)}
.go:disabled{opacity:.6}
.go:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
.done{display:grid;justify-items:center;gap:12px;text-align:center;padding:24px 0 8px}
.done .big{width:72px;height:72px;border-radius:99px;display:grid;place-items:center;background:#d6efdc;color:var(--green)}
.done .big svg{width:38px;height:38px}
.done p{max-width:36ch;color:var(--ink2);font-weight:500;margin:0}
.done .big.warn{background:var(--redsoft);color:var(--red)}
`;

const shell = (title, inner, script = "") => `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${esc(title)}</title>${FONT}<style>${WARM_CSS}</style></head><body><div class="page"><div class="brand"><span class="mark">M</span><span>Mentor</span></div><main class="sheet">${inner}</main></div>${script}</body></html>`;

export const receivedPage = (full = true) => {
  const inner = `<div class="done" role="status"><span class="big">${icon("check")}</span><h1>Đã nhận hồ sơ</h1><p>Thường duyệt trong 1–2 ngày. Có kết quả, chúng tôi gửi email.</p></div>`;
  return full ? shell("Đã nhận hồ sơ", inner) : inner;
};
export const noticePage = (title, text) =>
  shell(title, `<div class="done" role="status"><span class="big warn">${icon("x")}</span><h1>${esc(title)}</h1><p>${esc(text)}</p></div>`);

const SUBJECTS = ["Toán", "Vật lí", "Hóa học", "Sinh học", "Ngữ văn", "Tiếng Anh", "Lịch sử", "Địa lí", "Tin học", "Môn khác"];
const LEVELS = ["Tiểu học", "THCS", "THPT", "Đại học"];

export function hoSoPage({ t, email, reason }) {
  const inner = `<form id="form" method="post" action="/api/ho-so" enctype="multipart/form-data" novalidate style="display:grid;gap:24px">
<input type="hidden" name="t" value="${esc(t)}">
<header><h1>Kê khai hồ sơ giáo viên</h1><span class="who">${icon("mail")}<span>${esc(email)}</span></span></header>
${reason ? `<div class="banner" role="note">${icon("x")}<span><b>Lần trước bị từ chối</b>${esc(reason)}</span></div>` : ""}
<div class="row2">
<div class="f" data-f="name"><label class="lbl" for="name">Họ và tên</label><input type="text" id="name" name="full_name" autocomplete="name"><span class="err">Điền ô này.</span></div>
<div class="f" data-f="work"><label class="lbl" for="work">Nơi công tác</label><input type="text" id="work" name="workplace" autocomplete="organization" placeholder="Tên trường, trung tâm"><span class="err">Điền ô này.</span></div>
</div>
<div class="f" data-f="subj"><span class="lbl" id="subjL">Môn dạy</span>
<details class="multi" id="multi"><summary aria-labelledby="subjL"><span id="subjTxt" class="ph">Chọn môn</span>${icon("chev")}</summary>
<div class="panel">${SUBJECTS.map((s) => `<label><input type="checkbox" name="subjects" value="${s}">${s}</label>`).join("")}</div></details>
<span class="err">Chọn ít nhất một môn.</span></div>
<fieldset data-f="lvl"><legend>Cấp dạy</legend>
<div class="chips">${LEVELS.map((l) => `<label class="chip"><input type="checkbox" name="level" value="${l}"><span>${l}</span></label>`).join("")}</div>
<span class="err">Chọn ít nhất một cấp.</span></fieldset>
<div class="row2">
<div class="f" data-f="deg"><label class="lbl" for="deg">Bằng cấp hoặc chứng chỉ sư phạm</label><input type="text" id="deg" name="cert_kind" placeholder="Ví dụ: Cử nhân Sư phạm Toán"><span class="err">Điền ô này.</span></div>
<div class="f" data-f="num"><label class="lbl" for="num">Số hiệu</label><input type="text" id="num" name="cert_number" autocomplete="off"><span class="err">Điền ô này.</span></div>
</div>
<fieldset data-f="shots"><legend>Ảnh bằng hoặc chứng chỉ</legend>
<label class="drop2" id="drop2">${icon("image")}<b>Chọn 1 đến 3 ảnh</b><span class="hint">Rõ nét, thấy họ tên và số hiệu</span><input type="file" class="sr" id="pick" accept="image/*" multiple></label>
<div class="shots" id="shots"></div><span class="err">Thêm ít nhất một ảnh.</span></fieldset>
<label class="pledge" data-f="pledge"><input type="checkbox" id="pledge" name="pledge" value="1"><span>Tôi cam đoan thông tin trên là đúng và chịu trách nhiệm về nội dung khóa học tôi đăng.<span class="err">Cần đánh dấu ô này.</span></span></label>
<div><button type="submit" class="go" id="go">Gửi hồ sơ</button><p class="err" id="neterr" style="margin-top:10px">Chưa gửi được, bạn thử lại nhé.</p></div>
</form>`;
  const x = icon("x");
  const script = `<script>
(function(){
var $=function(s,r){return(r||document).querySelector(s)},$$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))};
var files=[],shots=$("#shots"),form=$("#form");
function sync(){
  $("#drop2").hidden=files.length>=3;
  shots.innerHTML="";
  files.forEach(function(f,i){
    var d=document.createElement("div");d.className="shot";
    d.innerHTML='<img alt="Ảnh chứng chỉ '+(i+1)+'"><button type="button" aria-label="Bỏ ảnh">${x.replace(/'/g, "\\'")}</button>';
    d.querySelector("img").src=URL.createObjectURL(f);
    d.querySelector("button").addEventListener("click",function(){files.splice(i,1);sync()});
    shots.appendChild(d);
  });
  if(files.length)$('[data-f="shots"]').classList.remove("bad");
}
// shrink phone photos (max 1600 px, JPEG) so they stay well under the 5 MB limit
function shrink(file){
  return new Promise(function(ok){
    var img=new Image(),u=URL.createObjectURL(file);
    img.onload=function(){
      var k=Math.min(1,1600/Math.max(img.width,img.height)),c=document.createElement("canvas");
      c.width=Math.round(img.width*k);c.height=Math.round(img.height*k);
      c.getContext("2d").drawImage(img,0,0,c.width,c.height);
      c.toBlob(function(b){ok(b&&b.size<file.size?new File([b],"anh.jpg",{type:"image/jpeg"}):file)},"image/jpeg",.85);
    };
    img.onerror=function(){ok(file)};img.src=u;
  });
}
$("#pick").addEventListener("change",function(e){
  var pick=[].slice.call(e.target.files).slice(0,3-files.length);e.target.value="";
  Promise.all(pick.map(shrink)).then(function(r){files=files.concat(r);sync()});
});
function subjTxt(){
  var v=$$('input[name="subjects"]:checked').map(function(x){return x.value}),t=$("#subjTxt");
  t.textContent=v.length?(v.length>2?v.length+" môn: "+v.slice(0,2).join(", ")+"…":v.join(", ")):"Chọn môn";
  t.classList.toggle("ph",!v.length);
}
function check(){
  var bad=0;
  function flag(k,b){$('[data-f="'+k+'"]').classList.toggle("bad",b);if(b)bad++}
  ["name","work","deg","num"].forEach(function(k){flag(k,!$("#"+k).value.trim())});
  flag("subj",!$$('input[name="subjects"]:checked').length);
  flag("lvl",!$$('input[name="level"]:checked').length);
  flag("shots",files.length===0);
  flag("pledge",!$("#pledge").checked);
  return bad;
}
form.addEventListener("input",function(){["name","work","deg","num"].forEach(function(k){if($("#"+k).value.trim())$('[data-f="'+k+'"]').classList.remove("bad")})});
form.addEventListener("change",function(){
  subjTxt();
  if($$('input[name="subjects"]:checked').length)$('[data-f="subj"]').classList.remove("bad");
  if($$('input[name="level"]:checked').length)$('[data-f="lvl"]').classList.remove("bad");
  if($("#pledge").checked)$('[data-f="pledge"]').classList.remove("bad");
});
form.addEventListener("submit",function(e){
  e.preventDefault();
  if(check()){var f=$(".bad");if(f)(f.querySelector("input,summary")||f).scrollIntoView({block:"center"});return}
  var fd=new FormData(form);fd.delete("photos");files.forEach(function(f){fd.append("photos",f,f.name)});
  var b=$("#go");b.disabled=true;$("#neterr").style.display="none";
  fetch("/api/ho-so",{method:"POST",body:fd}).then(function(r){return r.text().then(function(t){return[r.ok,t]})}).then(function(a){
    var m=new DOMParser().parseFromString(a[1],"text/html").querySelector(".sheet");
    if(m){$(".sheet").innerHTML=m.innerHTML;window.scrollTo(0,0)}else throw 0;
  }).catch(function(){b.disabled=false;$("#neterr").style.display="block"});
});
})();
</script>`;
  return shell("Kê khai hồ sơ giáo viên", inner, script);
}

// ----- admin -----
const ADMIN_CSS = `
*{box-sizing:border-box}
:root{color-scheme:light;--paper:#F2F0F5;--surface:#FAF9FB;--ink:#2B283F;--ink2:#5F5B74;--ink3:#8D89A0;--rule:#E4E0EC;--rs:#D2CCE0;--tim:#5A4BC0;--timink:#46399E;--timsoft:#E9E5F6;--do:#B23C3C;--dosoft:#F6E8E8;--vang:#F0D76E;--xanh:#1D7052;--xanhsoft:#E0EEE7;--cam:#925409;--camsoft:#F5EADC}
body{margin:0;background:var(--paper);color:var(--ink);font:400 15px/1.5 Lexend,system-ui,sans-serif;min-height:100vh}
h1,h2,h3{margin:0;line-height:1.2;font-weight:600}
svg{display:block;max-width:100%}
button,input,textarea{font:inherit;color:inherit}
[hidden]{display:none!important}
:focus-visible{outline:3px solid var(--tim);outline-offset:3px;border-radius:6px}
.top{display:flex;align-items:center;gap:14px;padding:10px clamp(12px,3vw,28px);background:var(--surface);border-bottom:1px solid var(--rs)}
.mk{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;background:var(--tim);color:#fff;font-weight:700;font-size:18px;box-shadow:inset 0 -3px 0 rgba(0,0,0,.18)}
.top .nm{font-weight:700}.top .sp{flex:1}.top .me{color:var(--ink2);font-size:.88em}
.tabs2{display:flex;flex-wrap:wrap;gap:2px;padding:0 clamp(12px,3vw,28px);background:var(--surface);border-bottom:1px solid var(--rs)}
.tabs2 button{display:inline-flex;align-items:center;gap:8px;min-height:46px;padding:0 14px;border:0;border-bottom:3px solid transparent;background:transparent;color:var(--ink2);font-weight:500;cursor:pointer}
.tabs2 button[aria-selected=true]{color:var(--timink);border-bottom-color:var(--tim);font-weight:600}
.count{min-width:22px;padding:1px 7px;border-radius:99px;background:var(--rule);color:var(--ink2);font-size:.8em;font-weight:600;text-align:center}
.tabs2 [aria-selected=true] .count{background:var(--timsoft);color:var(--timink)}
.count.hot{background:var(--vang);color:#3A3000}
.wrap{max-width:1240px;margin:0 auto;padding:18px clamp(12px,3vw,28px) 60px}
.split{display:grid;grid-template-columns:330px minmax(0,1fr);gap:18px;align-items:start}
.queue{list-style:none;margin:0;padding:0;background:var(--surface);border:1px solid var(--rs);border-radius:10px;overflow:hidden}
.queue li+li{border-top:1px solid var(--rule)}
.qi{display:grid;gap:2px;width:100%;padding:12px 14px;border:0;background:transparent;text-align:left;cursor:pointer;border-left:4px solid transparent;min-height:56px}
.qi:hover{background:var(--paper)}
.qi[aria-current=true]{background:var(--timsoft);border-left-color:var(--tim)}
.qi b{font-weight:600}
.qi .m{color:var(--ink2);font-size:.86em;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center}
.detail{background:var(--surface);border:1px solid var(--rs);border-radius:10px;padding:clamp(14px,2.5vw,24px);display:grid;gap:20px;min-width:0}
.detail h2{font-size:1.25em}
.sheet-bar{display:none}
.dh{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}.dh .sp{flex:1}
.muted{color:var(--ink2)}.small{font-size:.82em}
dl.kv{display:grid;grid-template-columns:150px minmax(0,1fr);gap:8px 16px;margin:0}
dl.kv dt{color:var(--ink2)}dl.kv dd{margin:0;overflow-wrap:anywhere}
@media(max-width:560px){dl.kv{grid-template-columns:minmax(0,1fr);gap:0}dl.kv dt{margin-top:8px;font-size:.86em}}
.prev{padding:10px 12px;border-radius:8px;background:var(--dosoft);color:var(--do);font-weight:500}
.sec{display:grid;gap:8px}
.sec>h3{font-size:.8em;letter-spacing:.04em;text-transform:uppercase;color:var(--ink2)}
.photos{display:flex;flex-wrap:wrap;gap:12px}
.photo{padding:0;border:1px solid var(--rs);border-radius:8px;overflow:hidden;background:#fff;cursor:zoom-in;width:200px}
.photo img{width:100%;display:block;min-height:60px}
.photo span{display:block;padding:4px 8px;font-size:.8em;color:var(--ink2);background:var(--paper);text-align:left}
.ok-flag{color:var(--xanh);font-weight:600}
table.t{width:100%;border-collapse:collapse}
table.t th{text-align:left;font-size:.78em;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);padding:8px 10px;border-bottom:1px solid var(--rs)}
table.t td{padding:9px 10px;border-bottom:1px solid var(--rule);vertical-align:middle}
table.t tr:last-child td{border-bottom:0}
.tag{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:99px;font-size:.78em;font-weight:600;background:var(--timsoft);color:var(--timink)}
.tag.new{background:var(--vang);color:#3A3000}.tag.ok{background:var(--xanhsoft);color:var(--xanh)}.tag.wait{background:var(--camsoft);color:var(--cam)}.tag.err{background:var(--dosoft);color:var(--do)}
.actions{display:grid;gap:12px;padding-top:16px;border-top:1px solid var(--rule)}
.btns{display:flex;flex-wrap:wrap;gap:10px}
.b{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 20px;border-radius:8px;border:1.5px solid var(--rs);background:var(--surface);font-weight:600;cursor:pointer}
.b:hover{border-color:var(--ink3)}
.b.yes{background:#1D6F4F;border-color:#1D6F4F;color:#fff}.b.yes:hover{background:#175B41}
.b.no{color:var(--do);border-color:var(--do)}.b.no:hover{background:var(--dosoft)}
.b.no.solid{background:#A93434;border-color:#A93434;color:#fff}
.b svg{width:18px;height:18px}
.b:disabled{opacity:.6;cursor:wait}
.reason{display:grid;gap:8px}.reason label{font-weight:600}
.reason textarea{width:100%;min-height:76px;padding:10px 12px;border-radius:8px;border:1.5px solid var(--rs);background:var(--paper);resize:vertical}
.reason textarea:focus{outline:3px solid var(--tim);border-color:var(--tim)}
.reason.bad textarea{border-color:var(--do)}
.reason .e{display:none;color:var(--do);font-size:.85em;font-weight:500}.reason.bad .e{display:block}
.quick{display:flex;flex-wrap:wrap;gap:6px}
.quick button{min-height:38px;padding:0 12px;border-radius:99px;border:1.5px solid var(--rs);background:var(--surface);font-size:.88em;cursor:pointer}
.quick button:hover{border-color:var(--tim)}
.empty{padding:56px 16px;text-align:center;color:var(--ink2);background:var(--surface);border:1px dashed var(--rs);border-radius:10px}
.empty svg{margin:0 auto 8px;width:32px;height:32px;color:var(--xanh)}
.bar2{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:14px}
.search{display:flex;align-items:center;gap:8px;flex:1;min-width:220px;max-width:460px;min-height:44px;border-radius:8px;padding:0 12px;border:1.5px solid var(--rs);background:var(--surface)}
.search:focus-within{border-color:var(--tim)}
.search input{flex:1;border:0;outline:0;background:transparent;min-width:0}
.search svg{width:20px;height:20px;color:var(--ink3);flex:none}
.tbl{background:var(--surface);border:1px solid var(--rs);border-radius:10px;overflow-x:auto}
.tbl .t td .sub{display:block;color:var(--ink2);font-size:.85em}
.tbl .b{min-height:38px;padding:0 12px;font-size:.9em;white-space:nowrap}
.show-s{display:none!important}
.mailtxt{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.9em;color:var(--ink2);margin:4px 0 0}
dialog{border:1.5px solid var(--rs);border-radius:14px;background:var(--surface);color:var(--ink);padding:22px}
dialog::backdrop{background:rgba(20,16,40,.55)}
dialog.sm{width:min(460px,calc(100vw - 32px))}
dialog h2{font-size:1.15em;margin-bottom:6px}
dialog .acts{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:10px;margin-top:18px}
dialog .reason{margin-top:12px}
dialog.light{padding:10px;max-width:min(900px,96vw)}
dialog.light img{max-height:80vh;width:auto;margin:0 auto}
.temp{margin:14px 0 4px;padding:14px;border-radius:10px;background:var(--paper);border:1.5px dashed var(--rs);text-align:center}
.temp code{display:block;font:700 1.6em/1.3 ui-monospace,Consolas,monospace;letter-spacing:.06em;user-select:all}
.toast{position:fixed;left:50%;transform:translateX(-50%);bottom:24px;z-index:80;background:var(--ink);color:#fff;padding:12px 18px;border-radius:10px;max-width:calc(100vw - 32px)}
.gate{max-width:420px;margin:12vh auto;padding:0 16px;display:grid;gap:14px}
.gate input{min-height:46px;padding:0 12px;border-radius:8px;border:1.5px solid var(--rs);background:var(--surface)}
@media(max-width:880px){
.split{grid-template-columns:minmax(0,1fr)}
.split .detail{display:none}
.split[data-open] .queue{display:none}
.split[data-open] .detail{display:grid;position:fixed;inset:0;z-index:60;border-radius:0;border:0;overflow-y:auto;align-content:start;padding:0 16px;gap:16px}
.split[data-open] .sheet-bar{display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:2;margin:0 -16px;padding:8px 12px;background:var(--surface);border-bottom:1px solid var(--rs)}
.split[data-open] .sheet-bar b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.split[data-open] .actions{position:sticky;bottom:0;background:var(--surface);margin:0 -16px;padding:12px 16px calc(12px + env(safe-area-inset-bottom))}
.hide-s{display:none}.show-s{display:block!important}
.photo{width:calc(50% - 6px)}
table.req,table.req tbody,table.req tr,table.req td{display:block}
table.req td{border-bottom:0;text-align:left!important}
table.req tr{padding:6px 4px 12px;border-bottom:1px solid var(--rule)}
table.req .b{width:100%;margin-top:4px}
}
@media(max-width:640px){.tabs2 button{flex:1 1 45%;justify-content:center}}
`;

export function adminPage() {
  const ic = JSON.stringify(Object.fromEntries(Object.keys(IC).map((k) => [k, icon(k)])));
  return `<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex"><title>Quản trị</title>${FONT}<style>${ADMIN_CSS}</style></head><body>
<div id="gate" class="gate" hidden><h1>Mentor · Quản trị</h1><p class="muted">Nhập khóa quản trị. Trình duyệt này sẽ nhớ khóa.</p><input id="key" type="password" autocomplete="off" aria-label="Khóa quản trị"><button class="b yes" id="keyGo" type="button">Vào</button><p class="muted" id="keyErr" style="color:var(--do)" hidden>Khóa chưa đúng.</p></div>
<div id="app" hidden>
<header class="top"><span class="mk" aria-hidden="true">M</span><span class="nm">Mentor · Quản trị</span><span class="sp"></span><span class="me">Chủ hệ thống</span></header>
<nav class="tabs2" role="tablist" aria-label="Mục">
<button role="tab" data-t="gv" aria-selected="true">Giáo viên chờ duyệt <span class="count hot" id="c-gv">0</span></button>
<button role="tab" data-t="kh" aria-selected="false">Khóa học chờ duyệt <span class="count hot" id="c-kh">0</span></button>
<button role="tab" data-t="dang" aria-selected="false">Đang đăng <span class="count" id="c-dang">0</span></button>
<button role="tab" data-t="tk" aria-selected="false">Tài khoản <span class="count" id="c-tk">0</span></button>
<button role="tab" data-t="thu" aria-selected="false">Thư chưa gửi <span class="count" id="c-thu">0</span></button>
</nav>
<main class="wrap"><section id="p-gv"></section><section id="p-kh" hidden></section><section id="p-dang" hidden></section><section id="p-tk" hidden></section><section id="p-thu" hidden></section></main>
</div>
<dialog class="sm" id="cf" aria-labelledby="cf-h"><h2 id="cf-h"></h2><p class="muted" id="cf-p"></p><div class="acts"><button type="button" class="b" id="cf-no">Hủy</button><button type="button" class="b yes" id="cf-yes">Duyệt</button></div></dialog>
<dialog class="sm" id="dlg" aria-labelledby="dlg-h"><h2 id="dlg-h"></h2><p class="muted">Học sinh đã tải về vẫn học tiếp được.</p>
<div class="reason" id="rm-reason"><label for="rm-why">Lý do gỡ</label><div class="quick"><button type="button" data-q="Nội dung chưa đúng">Nội dung chưa đúng</button><button type="button" data-q="Vi phạm bản quyền">Vi phạm bản quyền</button><button type="button" data-q="Giáo viên xin gỡ">Giáo viên xin gỡ</button></div><textarea id="rm-why" rows="3"></textarea><span class="e">Cần ghi lý do.</span></div>
<div class="acts"><button type="button" class="b" id="dlg-no">Giữ lại</button><button type="button" class="b no solid" id="dlg-yes">Gỡ và gửi lý do</button></div></dialog>
<dialog class="sm" id="pw" aria-labelledby="pw-h"><h2 id="pw-h"></h2>
<div id="pw-ask"><p class="muted">Mật khẩu cũ sẽ không dùng được nữa.</p><div class="acts"><button type="button" class="b" id="pw-no">Hủy</button><button type="button" class="b yes" id="pw-yes">Đặt lại</button></div></div>
<div id="pw-show" hidden><p class="muted">Mật khẩu tạm. Chỉ hiện một lần.</p><div class="temp"><code id="pw-code"></code></div><div class="acts"><button type="button" class="b yes" id="pw-done">Xong</button></div></div></dialog>
<dialog class="light" id="light" aria-label="Ảnh chứng chỉ"><div id="light-box"></div><div class="acts"><button type="button" class="b" id="light-x">Đóng</button></div></dialog>
<script>
(function(){
var IC=${ic};
var root=document.documentElement;
var $=function(s,r){return(r||document).querySelector(s)};
var esc=function(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})};
var KEY="";try{KEY=localStorage.getItem("mentor-admin-key")||""}catch(e){}
var T=[],C=[],D=[],A=[],R=[],O=[],opened=false,tabNow="gv",sel={gv:null,kh:null},q="",qa="",pendingConfirm=null,pendingRm=null,pendingPw=null;
var blobs={};

function api(method,path,data){
  return fetch(path,{method:method,headers:{"x-admin-key":KEY,"content-type":"application/json"},body:data?JSON.stringify(data):undefined}).then(function(r){
    if(r.status===403&&path.indexOf("/photo/")<0){showGate(true);throw new Error("forbidden")}
    return r.status===204?{}:r.json().then(function(j){if(!r.ok)throw new Error(j.error||"error");return j});
  });
}
function toast(m){var o=$(".toast");if(o)o.remove();var el=document.createElement("div");el.className="toast";el.setAttribute("role","status");el.textContent=m;document.body.appendChild(el);setTimeout(function(){el.remove()},4200)}
var ERR={script_missing:"Chưa nối Apps Script (SCRIPT_URL).",script_failed:"Apps Script báo lỗi, bạn thử lại sau.",reason_required:"Cần ghi lý do.",bad_state:"Mục này đã được xử lý rồi."};
function oops(e){if(e.message!=="forbidden")toast(ERR[e.message]||"Chưa làm được: "+e.message)}
var empty=function(m){return'<div class="empty">'+IC.check+m+"</div>"};
function fmt(iso){if(!iso)return"";var d=new Date(iso);return isNaN(d)?"":d.toLocaleString("vi-VN",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"})}

function actions(kind){
  var quick=kind==="gv"?["Ảnh mờ, không đọc được","Số hiệu không khớp","Thiếu thông tin"]:["Thiếu đáp án","Nội dung chưa đúng cấp","Tên khóa chưa rõ"];
  return'<div class="actions" data-kind="'+kind+'"><div class="btns"><button type="button" class="b yes" data-do="yes">'+IC.check+'Duyệt</button><button type="button" class="b no" data-do="no">Từ chối</button></div>'+
  '<div class="reason" hidden><label for="why-'+kind+'">Lý do từ chối</label><div class="quick">'+quick.map(function(x){return'<button type="button" data-q="'+esc(x)+'">'+esc(x)+"</button>"}).join("")+'</div><textarea id="why-'+kind+'" rows="3"></textarea><span class="e">Cần ghi lý do.</span><div class="btns"><button type="button" class="b no solid" data-do="send">Từ chối và gửi lý do</button><button type="button" class="b" data-do="back">Hủy</button></div></div></div>';
}
var bar=function(t){return'<div class="sheet-bar"><button type="button" class="b" data-back>← Danh sách</button><b>'+esc(t)+"</b></div>"};
var prevBox=function(r){return r?'<div class="prev"><b>Lần trước bị từ chối:</b> '+esc(r)+"</div>":""};

function renderGV(){
  var p=$("#p-gv");
  if(!T.length){p.innerHTML=empty("Không có hồ sơ chờ duyệt.");return}
  if(!T.some(function(t){return t.id===sel.gv}))sel.gv=T[0].id;
  var t=T.filter(function(x){return x.id===sel.gv})[0],d=t.decl||{};
  p.innerHTML='<div class="split"'+(opened?" data-open":"")+'><ul class="queue">'+T.map(function(x){return'<li><button class="qi" data-id="'+x.id+'" aria-current="'+(x.id===sel.gv)+'"><b>'+esc(x.display_name)+'</b><span class="m"><span>'+esc(fmt(x.submitted_at))+"</span>"+(x.reject_reason?'<span class="tag err">Nộp lại</span>':"")+"</span></button></li>"}).join("")+
  '</ul><article class="detail">'+bar(t.display_name)+'<div class="dh"><h2>'+esc(t.display_name)+'</h2><span class="sp"></span><span class="muted small">Nộp '+esc(fmt(t.submitted_at))+"</span></div>"+prevBox(t.reject_reason)+
  '<dl class="kv"><dt>Tài khoản</dt><dd>@'+esc(t.username)+"</dd><dt>Email</dt><dd>"+esc(t.email)+"</dd><dt>Họ tên khai</dt><dd>"+esc(d.full_name)+"</dd><dt>Nơi công tác</dt><dd>"+esc(d.workplace)+"</dd><dt>Môn dạy</dt><dd>"+esc((d.subjects||[]).join(", "))+"</dd><dt>Cấp dạy</dt><dd>"+esc(d.level)+"</dd><dt>Bằng, chứng chỉ</dt><dd>"+esc(d.cert_kind)+"</dd><dt>Số hiệu</dt><dd>"+esc(d.cert_number)+'</dd><dt>Cam đoan</dt><dd><span class="ok-flag">Đã cam đoan</span></dd></dl>'+
  '<div class="sec"><h3>Ảnh ('+(d.photos||[]).length+')</h3><div class="photos">'+(d.photos||[]).map(function(ph,i){return'<button type="button" class="photo" data-photo="'+esc(ph.key)+'"><img alt="Ảnh '+(i+1)+'" data-src="'+esc(ph.key)+'"><span>Ảnh '+(i+1)+"</span></button>"}).join("")+"</div></div>"+
  actions("gv")+"</article></div>";
  loadPhotos();
}
function loadPhotos(){
  document.querySelectorAll("img[data-src]").forEach(function(img){
    var k=img.dataset.src;
    if(blobs[k]){img.src=blobs[k];return}
    fetch("/api/admin/photo/"+k,{headers:{"x-admin-key":KEY}}).then(function(r){return r.blob()}).then(function(b){blobs[k]=URL.createObjectURL(b);img.src=blobs[k]}).catch(function(){});
  });
}
function renderKH(){
  var p=$("#p-kh");
  if(!C.length){p.innerHTML=empty("Không có khóa chờ duyệt.");return}
  if(!C.some(function(c){return c.course_id===sel.kh}))sel.kh=C[0].course_id;
  var c=C.filter(function(x){return x.course_id===sel.kh})[0],e=c.entry||{};
  var kind=function(x){return'<span class="tag '+(x.kind==="new"?"new":"wait")+'">'+(x.kind==="new"?"Mới":"Cập nhật")+"</span>"};
  var rows=Object.keys(e).filter(function(k){return typeof e[k]==="string"||typeof e[k]==="number"}).filter(function(k){return !/(^id$|_id$|url|sha|bytes|file)/.test(k)}).slice(0,8);
  p.innerHTML='<div class="split"'+(opened?" data-open":"")+'><ul class="queue">'+C.map(function(x){return'<li><button class="qi" data-id="'+esc(x.course_id)+'" aria-current="'+(x.course_id===sel.kh)+'"><b>'+esc(x.title)+'</b><span class="m">'+kind(x)+"<span>"+esc(x.teacher?x.teacher.name:"")+"</span><span>"+esc(fmt(x.updated_at))+"</span></span></button></li>"}).join("")+
  '</ul><article class="detail">'+bar(c.title)+'<div class="dh"><h2>'+esc(c.title)+"</h2>"+kind(c)+'<span class="tag">Bản '+c.version+"</span></div>"+
  '<dl class="kv"><dt>Giáo viên</dt><dd>'+esc(c.teacher?c.teacher.name:"")+' <span class="muted">· '+esc(c.teacher?c.teacher.email:"")+" · hồ sơ đã duyệt</span></dd><dt>Mã khóa</dt><dd>"+esc(c.course_id)+"</dd>"+
  (c.zip_bytes?"<dt>Dung lượng</dt><dd>"+(c.zip_bytes/1048576).toFixed(1)+" MB</dd>":"")+rows.map(function(k){return"<dt>"+esc(k)+"</dt><dd>"+esc(e[k])+"</dd>"}).join("")+"</dl>"+actions("kh")+"</article></div>";
}
function renderDang(){
  var p=$("#p-dang"),s=q.toLowerCase();
  var rows=D.filter(function(d){return(d.title+" "+(d.teacher?d.teacher.name:"")).toLowerCase().indexOf(s)>=0});
  p.innerHTML='<div class="bar2"><label class="search">'+IC.search+'<input id="q" type="search" placeholder="Tìm khóa, giáo viên" value="'+esc(q)+'" aria-label="Tìm"></label><span class="muted">'+rows.length+" khóa</span></div>"+
  '<div class="tbl"><table class="t"><thead><tr><th>Khóa học</th><th class="hide-s">Giáo viên</th><th class="hide-s">Bản</th><th class="hide-s">Cập nhật</th><th></th></tr></thead><tbody>'+
  (rows.length?rows.map(function(d){var n=d.teacher?d.teacher.name:"";return'<tr><td><b>'+esc(d.title)+'</b><span class="sub show-s">'+esc(n)+" · bản "+d.live_version+'</span></td><td class="hide-s">'+esc(n)+'</td><td class="hide-s">Bản '+d.live_version+'</td><td class="hide-s">'+esc(fmt(d.updated_at))+'</td><td style="text-align:right"><button class="b no" data-rm="'+esc(d.course_id)+'">Gỡ</button></td></tr>'}).join(""):'<tr><td colspan="5" class="muted" style="padding:28px;text-align:center">Không thấy khóa nào.</td></tr>')+"</tbody></table></div>";
  var i=$("#q");i.addEventListener("input",function(){q=i.value;var pos=i.selectionStart;renderDang();var n=$("#q");n.focus();n.setSelectionRange(pos,pos)});
}
function renderTK(){
  var p=$("#p-tk");
  var reqs=R.length?'<div class="sec" style="margin-bottom:18px"><h3>Yêu cầu đặt lại ('+R.length+')</h3><div class="tbl"><table class="t req"><tbody>'+R.map(function(r){return'<tr><td><b>@'+esc(r.username)+"</b>"+(r.display_name?" · "+esc(r.display_name):"")+'<span class="sub">'+esc(fmt(r.at))+(r.phone?" · gọi "+esc(r.phone):" · không để số điện thoại")+'</span></td><td style="text-align:right"><button class="b" data-pw="'+esc(r.username)+'">Đặt lại mật khẩu</button></td></tr>'}).join("")+"</tbody></table></div></div>":"";
  p.innerHTML=reqs+'<div class="bar2"><label class="search">'+IC.search+'<input id="qa" type="search" placeholder="Tìm tên, tên đăng nhập, email" value="'+esc(qa)+'" aria-label="Tìm"></label><span class="muted">'+A.length+" tài khoản</span></div>"+
  '<div class="tbl"><table class="t"><thead><tr><th>Tên</th><th class="hide-s">Tên đăng nhập</th><th class="hide-s">Email</th><th>Vai</th><th></th></tr></thead><tbody>'+
  (A.length?A.map(function(a){return'<tr><td><b>'+esc(a.display_name)+'</b><span class="sub show-s">@'+esc(a.username)+(a.email?" · "+esc(a.email):"")+'</span></td><td class="hide-s">'+esc(a.username)+'</td><td class="hide-s">'+(a.email?esc(a.email):'<span class="tag wait">Không có email</span>')+"</td><td>"+(a.role==="teacher"?"Giáo viên":"Học sinh")+'</td><td style="text-align:right"><button class="b" data-pw="'+esc(a.username)+'">Đặt lại mật khẩu</button></td></tr>'}).join(""):'<tr><td colspan="5" class="muted" style="padding:28px;text-align:center">Không thấy tài khoản nào.</td></tr>')+"</tbody></table></div>";
  var i=$("#qa");i.addEventListener("input",function(){qa=i.value;clearTimeout(renderTK.t);renderTK.t=setTimeout(function(){api("GET","/api/admin/accounts?q="+encodeURIComponent(qa)).then(function(r){A=r.accounts;var pos=i.selectionStart;renderTK();var n=$("#qa");n.focus();n.setSelectionRange(pos,pos)}).catch(oops)},250)});
}
function renderThu(){
  var p=$("#p-thu");
  if(!O.length){p.innerHTML=empty("Không có thư nào kẹt lại.");return}
  p.innerHTML='<p class="muted" style="margin:0 0 12px">Các thư chưa gửi được. Bạn chép mã hoặc liên kết gửi tay cho người nhận, rồi bấm Xong.</p><div class="tbl"><table class="t req"><tbody>'+O.map(function(m){
    var txt=String(m.html||"").replace(/<a [^>]*href="([^"]+)"[^>]*>/g," $1 ").replace(/<[^>]+>/g," ").replace(/&amp;/g,"&").replace(/\\s+/g," ").trim();
    return'<tr><td><b>'+esc(m.to)+'</b><span class="sub">'+esc(m.subject)+" · "+esc(fmt(m.at))+'</span><p class="mailtxt">'+esc(txt)+'</p></td><td style="text-align:right"><button class="b" data-ob="'+esc(m.key)+'">Xong</button></td></tr>'}).join("")+"</tbody></table></div>";
}
function counts(){
  $("#c-gv").textContent=T.length;$("#c-kh").textContent=C.length;$("#c-dang").textContent=D.length;$("#c-tk").textContent=A.length;$("#c-thu").textContent=O.length;
  $("#c-gv").classList.toggle("hot",T.length>0);$("#c-kh").classList.toggle("hot",C.length>0);$("#c-thu").classList.toggle("hot",O.length>0);
}
function all(){renderGV();renderKH();renderDang();renderTK();renderThu();counts()}
function load(){
  return Promise.all([api("GET","/api/admin/teachers?status=cho_duyet"),api("GET","/api/admin/courses?state=cho_duyet"),api("GET","/api/admin/courses?state=da_dang"),api("GET","/api/admin/accounts"),api("GET","/api/admin/resets"),api("GET","/api/admin/outbox")]).then(function(r){
    T=r[0].teachers;C=r[1].courses;D=r[2].courses;A=r[3].accounts;R=r[4].resets;O=r[5].outbox;all();
  }).catch(oops);
}
function tab(t){
  tabNow=t;opened=false;
  document.querySelectorAll(".tabs2 button").forEach(function(b){b.setAttribute("aria-selected",String(b.dataset.t===t))});
  ["gv","kh","dang","tk","thu"].forEach(function(k){$("#p-"+k).hidden=k!==t});
  all();
}
$(".tabs2").addEventListener("click",function(e){var b=e.target.closest("button");if(b)tab(b.dataset.t)});

function approve(kind){
  var id=sel[kind],btn=$("#cf-yes");btn.disabled=true;
  var done=kind==="gv"?api("POST","/api/admin/teachers/"+id+"/approve").then(function(){toast("Đã duyệt. Mã 6 số đã gửi về email giáo viên (hoặc nằm ở Thư chưa gửi).")}):api("POST","/api/admin/courses/"+encodeURIComponent(id)+"/approve").then(function(){toast("Đã duyệt. Khóa đã hiện cho học sinh.")});
  done.catch(oops).then(function(){btn.disabled=false;opened=false;load()});
}
function showPw(u){pendingPw=u;$("#pw-h").textContent="Đặt lại mật khẩu của @"+u+"?";$("#pw-ask").hidden=false;$("#pw-show").hidden=true;$("#pw").showModal()}

document.addEventListener("click",function(e){
  var t=e.target;
  if(t.closest("[data-back]")){opened=false;all();return}
  var qi=t.closest(".qi");
  if(qi){sel[tabNow]=qi.dataset.id;opened=true;all();var d=$(".split[data-open] .detail");if(d)d.scrollTop=0;return}
  var ph=t.closest(".photo");
  if(ph){var im=ph.querySelector("img");$("#light-box").innerHTML='<img alt="Ảnh chứng chỉ" src="'+esc(im.src)+'">';$("#light").showModal();return}
  var q2=t.closest("[data-q]");
  if(q2){var box=q2.closest(".reason");box.querySelector("textarea").value=q2.dataset.q;box.classList.remove("bad");return}
  var a=t.closest("[data-do]");
  if(a){
    var wrap=a.closest(".actions"),kind=wrap.dataset.kind,reason=wrap.querySelector(".reason"),btns=wrap.querySelector(".btns"),act=a.dataset.do;
    if(act==="no"){reason.hidden=false;btns.hidden=true;reason.querySelector("textarea").focus()}
    else if(act==="back"){reason.hidden=true;btns.hidden=false}
    else if(act==="yes"){
      var it=kind==="gv"?T.filter(function(x){return x.id===sel.gv})[0]:C.filter(function(x){return x.course_id===sel.kh})[0];
      pendingConfirm=kind;
      $("#cf-h").textContent=kind==="gv"?"Duyệt hồ sơ của "+it.display_name+"?":"Duyệt khóa “"+it.title+"”?";
      $("#cf-p").textContent=kind==="gv"?"Mã 6 số sẽ gửi về email của giáo viên.":(it.kind==="new"?"Khóa hiện cho học sinh ngay.":"Học sinh sẽ thấy bản mới.");
      $("#cf").showModal();
    }else{
      var why=reason.querySelector("textarea").value.trim();
      if(!why){reason.classList.add("bad");reason.querySelector("textarea").focus();return}
      var url=kind==="gv"?"/api/admin/teachers/"+sel.gv+"/reject":"/api/admin/courses/"+encodeURIComponent(sel.kh)+"/reject";
      a.disabled=true;
      api("POST",url,{reason:why}).then(function(){toast("Đã từ chối. Lý do đã gửi cho giáo viên.")}).catch(oops).then(function(){opened=false;load()});
    }
    return;
  }
  var rm=t.closest("[data-rm]");
  if(rm){pendingRm=D.filter(function(x){return x.course_id===rm.dataset.rm})[0];$("#dlg-h").textContent="Gỡ “"+pendingRm.title+"”?";$("#rm-why").value="";$("#rm-reason").classList.remove("bad");$("#dlg").showModal();return}
  var pw=t.closest("[data-pw]");
  if(pw){showPw(pw.dataset.pw);return}
  var ob=t.closest("[data-ob]");
  if(ob){api("DELETE","/api/admin/outbox/"+encodeURIComponent(ob.dataset.ob)).then(load).catch(oops)}
});
$("#cf-no").addEventListener("click",function(){$("#cf").close()});
$("#cf-yes").addEventListener("click",function(){$("#cf").close();if(pendingConfirm){approve(pendingConfirm);pendingConfirm=null}});
$("#dlg-no").addEventListener("click",function(){$("#dlg").close()});
$("#dlg-yes").addEventListener("click",function(){
  var why=$("#rm-why").value.trim();
  if(!why){$("#rm-reason").classList.add("bad");$("#rm-why").focus();return}
  $("#dlg").close();
  if(pendingRm){var d=pendingRm;pendingRm=null;api("POST","/api/admin/courses/"+encodeURIComponent(d.course_id)+"/remove",{reason:why}).then(function(){toast("Đã gỡ. Lý do đã gửi cho giáo viên.")}).catch(oops).then(load)}
});
$("#rm-reason").addEventListener("input",function(){$("#rm-reason").classList.remove("bad")});
$("#pw-no").addEventListener("click",function(){$("#pw").close()});
$("#pw-yes").addEventListener("click",function(){
  api("POST","/api/admin/accounts/"+encodeURIComponent(pendingPw)+"/reset-password").then(function(r){$("#pw-code").textContent=r.temp_password;$("#pw-ask").hidden=true;$("#pw-show").hidden=false}).catch(function(e){$("#pw").close();oops(e)});
});
$("#pw-done").addEventListener("click",function(){$("#pw").close();$("#pw-code").textContent="";toast("Đã đặt lại mật khẩu của @"+pendingPw+".");load()});
$("#light-x").addEventListener("click",function(){$("#light").close()});
$("#light").addEventListener("click",function(e){if(e.target.id==="light")$("#light").close()});

function showGate(bad){
  try{localStorage.removeItem("mentor-admin-key")}catch(e){}
  KEY="";$("#app").hidden=true;$("#gate").hidden=false;$("#keyErr").hidden=!bad;$("#key").value="";$("#key").focus();
}
function enter(){
  api("GET","/api/admin/teachers?status=cho_duyet").then(function(){
    try{localStorage.setItem("mentor-admin-key",KEY)}catch(e){}
    $("#gate").hidden=true;$("#app").hidden=false;load();
  }).catch(function(){});
}
$("#keyGo").addEventListener("click",function(){KEY=$("#key").value.trim();if(KEY)enter()});
$("#key").addEventListener("keydown",function(e){if(e.key==="Enter")$("#keyGo").click()});
if(KEY)enter();else showGate(false);
})();
</script></body></html>`;
}
