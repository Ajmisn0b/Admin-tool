let data = [];

function processFile(){
const file = document.getElementById('fileInput').files[0];
if(!file) return alert("اختر ملف");

file.text().then(text=>{
const lines = text.split("\n");
data = [];

lines.forEach(l=>{
let m = l.match(/<@(\d+)>.*\|\s*=\s*(\d+)/);
if(m){
data.push({id:m[1], num:parseInt(m[2]), raw:l});
}
});

render();
});
}

function render(){
const ul = document.getElementById("results");
ul.innerHTML="";
data.forEach((m,i)=>{
let li=document.createElement("li");
li.textContent = m.raw;
li.onclick = ()=>{
navigator.clipboard.writeText(m.id);
alert("تم النسخ");
};
ul.appendChild(li);
});
}

function saveFile(){
let content = data.map(m=>m.raw).join("\n");
let blob = new Blob([content],{type:"text/plain"});
let a = document.createElement("a");
a.href = URL.createObjectURL(blob);
a.download="output.txt";
a.click();
}
