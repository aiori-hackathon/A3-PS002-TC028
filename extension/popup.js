const API = "http://127.0.0.1:8000";
const purposes = [
  ["analytics","Analytics"],["personalization","Personalisation"],
  ["advertising","Advertising"],["email_marketing","Email marketing"]
];
const noticeFallback = "Demo privacy notice v1: essential storage runs the service; analytics measures usage; personalization remembers preferences; advertising supports promotions; email marketing sends promotional updates.";
let notice = null;
async function init(){
  const stored = await chrome.storage.local.get("detectedNotice");
  notice = stored.detectedNotice;
  if(notice){document.getElementById("site").textContent = notice.site;document.getElementById("summary").textContent = notice.summary.join(" ");}
  await refresh();
}
async function refresh(){
  const site = notice?.site || "demo.local";
  const host = document.getElementById("purposes");
  try{
    const res=await fetch(`${API}/api/consents?site=${encodeURIComponent(site)}`);
    const rows=await res.json();
    host.innerHTML="";
    purposes.forEach(([id,label])=>{
      const state=rows.find(x=>x.purpose===id)?.status || "not_set";
      const div=document.createElement("div");div.className="purpose";
      const name=document.createElement("label");name.textContent=`${label} · ${state}`;
      const btn=document.createElement("button");btn.textContent=state==="granted"?"Withdraw":"Allow";
      if(state==="granted")btn.className="off";
      btn.addEventListener("click",()=>save(id,state==="granted"?"withdrawn":"granted"));
      div.append(name,btn);host.append(div);
    });
  }catch(e){host.textContent="Backend unavailable. Start the FastAPI server.";}
}
async function save(purpose,decision){
  const site=notice?.site || "demo.local";
  const text=notice?.noticeText || noticeFallback;
  const res=await fetch(`${API}/api/consents`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({site,purpose,decision,notice_version:"v1",notice_text:text,reason:"User choice from browser extension"})});
  if(res.ok)refresh();else alert("Could not save this consent choice.");
}
init();
