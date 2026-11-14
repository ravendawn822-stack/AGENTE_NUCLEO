import tkinter as tk
from tkinter import ttk,messagebox
import json,threading,queue,time,math,statistics,sqlite3
from backend import *
COLORS={'hypothesis':'#aec5dc','candidate':'#f4c95d','validated':'#67be98','refuted':'#e49295','entity':'#d5dbe1'}
class Panel:
    def __init__(self,root):
        self.root=root;root.title('AGENTE_NUCLEO · PAINEL 02');root.geometry('1240x820')
        self.control=None;self.q=queue.Queue();self.path=None;self.last=0;self.nodes={};self.scores={};self.history=[];self.events=[];self.play=False;self.position=0;self.render_times=[]
        style=ttk.Style();style.theme_use('clam');style.configure('Treeview',rowheight=24)
        top=ttk.Frame(root,padding=8);top.pack(fill='x')
        self.agent=ttk.Combobox(top,values=['A','B','C','D','ORDER'],width=7,state='readonly');self.agent.set('C');self.agent.pack(side='left')
        for label,cmd in [('Iniciar diagnóstico',self.start),('Pausar',lambda:self.action('pause')),('Continuar',lambda:self.action('resume')),('Passo',lambda:self.action('step')),('Encerrar',lambda:self.action('stop'))]:ttk.Button(top,text=label,command=cmd).pack(side='left',padx=2)
        self.speed=ttk.Combobox(top,values=['Máxima','100 eventos/s','10 eventos/s','1 evento/s'],width=15,state='readonly');self.speed.current(0);self.speed.pack(side='left');self.speed.bind('<<ComboboxSelected>>',lambda e:self.set_speed())
        self.status=tk.StringVar(value='Diagnóstico visual separado da avaliação científica · atualização máxima 5 Hz')
        ttk.Label(root,textvariable=self.status,padding=8).pack(fill='x')
        self.live_stats=tk.StringVar(value='Nenhuma sessão diagnóstica em execução.')
        ttk.Label(root,textvariable=self.live_stats,padding=4).pack(fill='x');self.budget=0;self.consumed=0;self.memory_count=0;self.times=[];self.validations=[]
        tabs=ttk.Notebook(root);tabs.pack(fill='both',expand=True)
        self.frames={}
        for title in ['Ao vivo e grafo','Pontuações e memória','Replay','Comparação científica']:
            f=ttk.Frame(tabs,padding=8);tabs.add(f,text=title);self.frames[title]=f
        live=self.frames['Ao vivo e grafo']
        ttk.Label(live,text='Azul: hipótese · amarelo: candidata · verde: validada no contexto · vermelho: refutada · cinza: componente\nContorno: laranja selecionada · azul construída · violeta adquirida · cinza escuro testada. Clique no nó. Até 60 nós.').pack(anchor='w')
        self.canvas=tk.Canvas(live,height=330,bg='#f6f8fb');self.canvas.pack(fill='both',expand=True)
        self.detail=tk.Text(live,height=12,wrap='word',font=('Consolas',10));self.detail.pack(fill='x')
        mem=self.frames['Pontuações e memória']
        self.score_table=self.table(mem,['id','P','R','E','K','S','selecionada'])
        self.growth=tk.Canvas(mem,height=200,bg='white');self.growth.pack(fill='x')
        replay=self.frames['Replay'];bar=ttk.Frame(replay);bar.pack(fill='x')
        self.sessions=ttk.Combobox(bar,width=45,state='readonly');self.sessions.pack(side='left');self.sessions.bind('<<ComboboxSelected>>',lambda e:self.load_replay())
        ttk.Button(bar,text='Atualizar lista',command=self.list_sessions).pack(side='left')
        ttk.Button(bar,text='◀',command=lambda:self.move(-1)).pack(side='left');ttk.Button(bar,text='▶',command=lambda:self.move(1)).pack(side='left')
        ttk.Button(bar,text='Reproduzir / pausar',command=self.toggle).pack(side='left')
        self.slider=tk.Scale(replay,from_=0,to=0,orient='horizontal',command=self.seek);self.slider.pack(fill='x')
        self.replay_text=tk.Text(replay,height=13,wrap='word');self.replay_text.pack(fill='x')
        self.tree=tk.Canvas(replay,bg='#f6f8fb',height=270);self.tree.pack(fill='both',expand=True)
        comp=self.frames['Comparação científica'];line=ttk.Frame(comp);line.pack(fill='x')
        self.mode=ttk.Combobox(line,values=['candidates','time'],state='readonly',width=14);self.mode.current(0);self.mode.pack(side='left')
        self.cap=ttk.Combobox(line,values=['8','24'],state='readonly',width=8);self.cap.current(0);self.cap.pack(side='left')
        ttk.Button(line,text='Ler resultados científicos',command=self.compare).pack(side='left')
        self.comp_status=tk.StringVar(value='Leitura explícita; nenhuma execução científica é iniciada pelo painel.');ttk.Label(comp,textvariable=self.comp_status).pack(anchor='w')
        self.chart=tk.Canvas(comp,height=220,bg='white');self.chart.pack(fill='x')
        self.comp_table=self.table(comp,['agente','checkpoint','n','sucesso %','ms total','seleção ms','candidatos','memória'])
        root.protocol('WM_DELETE_WINDOW',self.close);self.list_sessions();root.after(200,self.poll)
    def table(self,parent,cols):
        f=ttk.Frame(parent);f.pack(fill='both',expand=True);t=ttk.Treeview(f,columns=cols,show='headings',height=10)
        for c in cols:t.heading(c,text=c);t.column(c,width=100)
        s=ttk.Scrollbar(f,command=t.yview);t.configure(yscrollcommand=s.set);s.pack(side='right',fill='y');t.pack(fill='both',expand=True);return t
    def start(self):
        if self.control is not None:return
        self.control=Control();self.set_speed();self.nodes={};self.scores={};self.history=[];self.last=0;self.path=None;self.times=[];self.validations=[];self.memory_count=0;self.consumed=0;self.budget=0
        threading.Thread(target=diagnose,args=(self.control,self.q,self.agent.get()),daemon=True).start()
    def action(self,a):
        if self.control:self.control.change(a);self.status.set('Diagnóstico: '+a)
    def set_speed(self):
        if self.control:self.control.delay=[0,.01,.1,1][self.speed.current()]
    def process(self,e):
        self.pending_status=f"Episódio {e['episode']} · {e['kind']} · evento {e['seq']} · diagnóstico"
        expr=e.get('expression') or e.get('expr');sid=e.get('id');kind=e['kind']
        if expr:
            sid=sid or ident(expr)
            if sid not in self.nodes:
                for node in subtrees(freeze(expr)):
                    nid=ident(node)
                    if nid not in self.nodes:self.nodes[nid]=dict(expr=node,state='entity',highlight='',last=e['seq'])
            n=self.nodes[sid];n['last']=e['seq']
            if 'state' in e:n['state']=e['state']
        if sid in self.nodes:
            n=self.nodes[sid]
            if kind in ('hypothesis_refuted','candidate_accepted'):n['highlight']='tested'
            if kind=='skill_selected':n['highlight']='selected';n['selected']=True
            if kind=='skill_constructed':n['highlight']='constructed'
            if kind=='skill_acquired':n['highlight']='acquired'
        if kind=='episode_start':
            self.budget=e['budget'];self.consumed=0
            self.scores={}
            for n in self.nodes.values():n['highlight']='';n['selected']=False
        if kind=='skill_score':self.scores[sid]=e
        if kind=='hypothesis_generated':self.consumed=e['consumed']
        if kind=='search_end':self.times.append(e['seconds'])
        if kind=='episode_end':self.validations.append(e['training_valid'])
        if kind=='memory_growth':self.history.append((e['episode'],e['count']));self.memory_count=e['count']
    def poll(self):
        try:
            while True:
                kind,msg=self.q.get_nowait()
                if kind=='started':self.path=Path(msg)
                elif kind in ('done','cancelled','error'):
                    self.control=None;self.status.set(kind+': '+msg);self.list_sessions()
        except queue.Empty:pass
        if self.path:
            try:
                batch=read_events(self.path,self.last,1000)
                if batch:
                    t=time.perf_counter()
                    for e in batch:self.process(e)
                    self.last=batch[-1]['seq'];self.draw();self.render_times.append(time.perf_counter()-t)
            except sqlite3.OperationalError:pass
        if self.play:self.move(1)
        self.root.after(200,self.poll)
    def draw(self):
        if hasattr(self,'pending_status'):self.status.set(self.pending_status)
        self.live_stats.set(f'Orçamento restante: {max(0,self.budget-self.consumed)} candidatos · memória ativa: {self.memory_count} · busca média diagnóstica: {1000*statistics.mean(self.times):.1f} ms · validação de treino: {sum(self.validations)}/{len(self.validations)}' if self.times else f'Orçamento restante: {max(0,self.budget-self.consumed)} candidatos · memória ativa: {self.memory_count}')
        c=self.canvas;c.delete('all');w=max(800,c.winfo_width());h=max(300,c.winfo_height())
        # Seleciona somente entidades armazenadas: prioriza destaques e estados úteis.
        ordered=sorted(self.nodes.items(),key=lambda kv:(bool(kv[1]['highlight']),kv[1]['state']=='validated',kv[1]['last']),reverse=True)[:60]
        pos={sid:(45+(i%10)*(w-90)/9,45+(i//10)*max(42,(h-85)/6)) for i,(sid,n) in enumerate(ordered)}
        for sid,n in ordered:
            for child in children(n['expr']):
                cid=ident(child)
                if cid in pos:c.create_line(*pos[sid],*pos[cid],fill='#c7d0da',arrow='last')
        for sid,n in ordered:
            x,y=pos[sid];outline={'selected':'#ed8c00','constructed':'#006bb6','acquired':'#8b36c6','tested':'#344552'}.get(n['highlight'],'#738294')
            item=c.create_oval(x-24,y-18,x+24,y+18,fill=COLORS[n['state']],outline=outline,width=3)
            label=c.create_text(x,y,text=text(n['expr'])[:9],font=('Segoe UI',8))
            for obj in (item,label):c.tag_bind(obj,'<Button-1>',lambda e,s=sid:self.inspect(s))
        self.score_table.delete(*self.score_table.get_children())
        for sid,s in sorted(self.scores.items(),key=lambda p:-p[1]['S']):
            self.score_table.insert('','end',values=(sid[:10],*[round(s[k],4) for k in ('P','R','E','K','S')],bool(self.nodes.get(sid,{}).get('selected'))))
        self.growth.delete('all')
        self.growth.create_text(10,12,anchor='w',text='Memória ativa após treinamento · sessão diagnóstica')
        if self.history:
            maximum=max(1,max(n for _,n in self.history));pts=[(35+i*max(10,(self.growth.winfo_width()-70)/max(1,len(self.history)-1)),175-n/maximum*130) for i,(_,n) in enumerate(self.history)]
            if len(pts)>1:self.growth.create_line(*[v for p in pts for v in p],fill='#007b83',width=3)
            for (x,y),(ep,n) in zip(pts,self.history):self.growth.create_text(x,y-10,text=str(n));self.growth.create_text(x,190,text=str(ep))
    def inspect(self,sid):
        obj=read_skill(self.path,sid) if self.path else {}
        obj.update(id=sid,expression=text(self.nodes[sid]['expr']),composition=[ident(c) for c in children(self.nodes[sid]['expr'])],score=self.scores.get(sid),note='Estados são contextuais. Seleção, construção e presença não são causalidade. Consulte ablações quando disponíveis.')
        self.detail.delete('1.0','end');self.detail.insert('end',json.dumps(obj,indent=2,ensure_ascii=False))
    def list_sessions(self):
        self.session_paths=sorted((ROOT/'sessions').glob('*/diagnostic.sqlite3'))
        self.sessions['values']=[p.parent.name for p in self.session_paths]
    def load_replay(self):
        if self.sessions.current()<0:return
        p=self.session_paths[self.sessions.current()].parent;self.events=[];last=0
        while True:
            rows=read_events(p,last,2000)
            if not rows:break
            self.events+=rows;last=rows[-1]['seq']
        self.slider.configure(to=max(0,len(self.events)-1));self.slider.set(0);self.seek(0)
    def toggle(self):self.play=not self.play
    def move(self,delta):
        if not self.events:return
        target=max(0,min(len(self.events)-1,self.position+delta));self.slider.set(target)
        if target==len(self.events)-1:self.play=False
    def seek(self,v):
        if not self.events:return
        self.position=int(float(v));e=self.events[self.position]
        self.replay_text.delete('1.0','end');self.replay_text.insert('end',json.dumps(e,indent=2,ensure_ascii=False))
        expr=next((x.get('expression') or x.get('expr') for x in reversed(self.events[:self.position+1]) if x.get('expression') or x.get('expr')),None)
        self.tree.delete('all')
        if expr:
            def draw(e,x,y,span):
                cs=children(e)
                for i,child in enumerate(cs):
                    cx=x+(i-(len(cs)-1)/2)*span;self.tree.create_line(x,y,cx,y+48,fill='#aaa');draw(child,cx,y+48,span/2)
                self.tree.create_oval(x-20,y-16,x+20,y+16,fill='#d4e7ee');self.tree.create_text(x,y,text=text(e) if not cs else {1:'+',2:'−',3:'×',20:'<',21:'=',30:'if'}[e[0]])
            draw(expr,max(700,self.tree.winfo_width())/2,25,250)
    def compare(self):
        p=EXP/'results'/'experiment.sqlite3'
        if not p.exists():return
        db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
        groups={}
        for (data,) in db.execute('SELECT data FROM episodes'):
            r=json.loads(data)
            if r['section']=='main' and r['phase']=='evaluation' and r['mode']==self.mode.get() and r['capacity']==int(self.cap.get()):groups.setdefault((r['agent'],r['step']),[]).append(r)
        db.close();self.comp_table.delete(*self.comp_table.get_children());self.chart.delete('all')
        colors={'A':'#777','B':'#007a7f','C':'#8249a5','D':'#ca741b','ORDER':'#5278bc'}
        for a in ['A','B','C','D','ORDER']:
            pts=[]
            for step in [0,8,16,24]:
                rs=groups.get((a,step),[])
                if not rs:continue
                mean=lambda k:statistics.mean(r[k] for r in rs)
                rate=100*mean('success');pts.extend((45+step*32,190-rate*1.5))
                self.comp_table.insert('','end',values=(a,step,len(rs),round(rate,2),round(1000*mean('total_seconds'),2),round(1000*mean('selection_seconds'),3),round(mean('candidates'),1),round(mean('memory'),1)))
            if len(pts)>=4:self.chart.create_line(*pts,fill=colors[a],width=2)
            self.chart.create_text(80+list(colors).index(a)*130,15,text=a,fill=colors[a])
        for y in [0,25,50,75,100]:self.chart.create_text(20,190-y*1.5,text=str(y)+'%')
        for x in [0,8,16,24]:self.chart.create_text(45+x*32,210,text=str(x))
        self.comp_status.set('Resultados reais; n<72 indica checkpoint parcial. ORDER é a referência por aquisição. Diagnósticos excluídos.')
    def close(self):
        if self.control:self.control.change('stop')
        if self.render_times:(ROOT/'render_measurements.json').write_text(json.dumps(dict(refresh_limit_hz=5,frames=len(self.render_times),mean_seconds=statistics.mean(self.render_times),max_seconds=max(self.render_times))))
        self.root.destroy()
if __name__=='__main__':
    root=tk.Tk();Panel(root);root.mainloop()
