import tkinter as tk
from tkinter import ttk, messagebox
import json, statistics, threading, queue
from data import *

class Panel:
    def __init__(self,root):
        self.root=root; root.title('AGENTE_NUCLEO · Observabilidade local'); root.geometry('1180x780')
        self.rows=[]; self.skills=[]; self.events=[]; self.pos=0; self.playing=False; self.q=queue.Queue()
        style=ttk.Style(); style.theme_use('clam'); style.configure('Treeview',rowheight=25)
        top=ttk.Frame(root,padding=10); top.pack(fill='x')
        self.source=ttk.Combobox(top,state='readonly',width=42); self.source.pack(side='left'); self.source.bind('<<ComboboxSelected>>',lambda e:self.load())
        self.filters={}
        for key,values in [('agent',['Todos','A','B','C']),('mode',['hypotheses','time']),('seed',['Todos','104729','130363','155921'])]:
            ttk.Label(top,text=key).pack(side='left',padx=5)
            box=ttk.Combobox(top,values=values,state='readonly',width=13); box.current(0); box.pack(side='left'); box.bind('<<ComboboxSelected>>',lambda e:self.refresh()); self.filters[key]=box
        self.diag=ttk.Button(top,text='Novo diagnóstico',command=self.diagnose); self.diag.pack(side='right')
        self.status=tk.StringVar(value='Dados locais · nenhuma conexão externa'); ttk.Label(root,textvariable=self.status,padding=8).pack(fill='x')
        tabs=ttk.Notebook(root); tabs.pack(fill='both',expand=True,padx=10,pady=5)
        self.pages={}
        for name in ['Visão geral','Execução e replay','Memória','Comparações']:
            f=ttk.Frame(tabs,padding=10); tabs.add(f,text=name); self.pages[name]=f
        self.summary=tk.StringVar(); ttk.Label(self.pages['Visão geral'],textvariable=self.summary,font=('Segoe UI',12),justify='left').pack(anchor='w')
        ttk.Label(self.pages['Visão geral'],text='Selecione um episódio para revisar seu registro. Históricos não têm sequência de hipóteses.',padding=10).pack(anchor='w')
        self.episodes=self.table(self.pages['Visão geral'],['linha','agente','fase','checkpoint','problema','sucesso','hipóteses','ms','habilidades'])
        self.episodes.bind('<<TreeviewSelect>>',lambda e:self.select_episode())
        self.episode_label=tk.StringVar(); ttk.Label(self.pages['Execução e replay'],textvariable=self.episode_label).pack(anchor='w')
        bar=ttk.Frame(self.pages['Execução e replay']); bar.pack(fill='x')
        for label,command in [('◀',lambda:self.step(-1)),('▶',lambda:self.step(1)),('Reproduzir / pausar',self.toggle)]: ttk.Button(bar,text=label,command=command).pack(side='left')
        self.slider=tk.Scale(bar,from_=0,to=0,orient='horizontal',command=self.seek); self.slider.pack(side='left',fill='x',expand=True)
        self.details=tk.Text(self.pages['Execução e replay'],height=14,wrap='word',font=('Consolas',10)); self.details.pack(fill='x')
        self.tree=tk.Canvas(self.pages['Execução e replay'],height=250,bg='#f3f6fa'); self.tree.pack(fill='both',expand=True)
        ttk.Label(self.pages['Memória'],text='Uso derivado = presença sintática em soluções posteriores à aquisição. Não mede contribuição causal.').pack(anchor='w')
        self.memory=self.table(self.pages['Memória'],['agente','semente','origem','profundidade','expressão','usos derivados','usos em acertos'])
        self.memory.bind('<<TreeviewSelect>>',lambda e:self.select_skill())
        self.relation=tk.StringVar(); ttk.Label(self.pages['Memória'],textvariable=self.relation,wraplength=1050).pack(fill='x')
        self.chart=tk.Canvas(self.pages['Comparações'],height=240,bg='white'); self.chart.pack(fill='x'); self.chart.bind('<Configure>',lambda e:self.draw_chart())
        self.comparison=self.table(self.pages['Comparações'],['agente','checkpoint','n','sucesso %','ms','hipóteses','habilidades','pico KiB'])
        self.rescan(); root.after(200,self.poll)
    def table(self,parent,columns):
        frame=ttk.Frame(parent); frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=columns,show='headings',height=10)
        for c in columns: tree.heading(c,text=c); tree.column(c,width=110,stretch=True)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y'); tree.pack(fill='both',expand=True); return tree
    def rescan(self):
        self.paths=sources(); self.source['values']=[('Diagnóstico ' if p.parent.name=='sessions' else 'EXP02 ')+p.name for p in self.paths]
        if self.paths: self.source.current(len(self.paths)-1); self.load()
    def load(self):
        try:
            self.path=self.paths[self.source.current()]; self.rows,self.skills=load(self.path)
            self.all_events={}
            if (self.path/'events.jsonl').exists():
                for line in (self.path/'events.jsonl').read_text(encoding='utf-8').splitlines():
                    e=json.loads(line); self.all_events.setdefault(e['episode'],[]).append(e)
            self.refresh()
        except Exception as ex: messagebox.showerror('Leitura',str(ex))
    def matches(self,r,agent=True):
        return all(self.filters[k].get()=='Todos' or str(r[k])==self.filters[k].get() for k in ('seed','mode')+ (('agent',) if agent else ()))
    def refresh(self):
        self.filtered=[(i,r) for i,r in enumerate(self.rows) if self.matches(r)]
        for widget in (self.episodes,self.memory,self.comparison): widget.delete(*widget.get_children())
        for i,r in self.filtered:
            self.episodes.insert('', 'end',iid=str(i),values=(i,r['agent'],r['phase'],r['step'],r['index'],r['success'],r['hypotheses'],round(1000*r['seconds'],2),r['skills']))
        evaluation=[r for _,r in self.filtered if r['phase']=='evaluation']; step=max((r['step'] for r in evaluation),default=0)
        latest=[r for r in evaluation if r['step']==step]
        desc=(f"Avaliação no checkpoint {step}: {100*statistics.mean(r['success'] for r in latest):.2f}% de sucesso; {1000*statistics.mean(r['seconds'] for r in latest):.2f} ms médios" if latest else 'Sessão diagnóstica: treino instrumentado; tempos não comparáveis aos experimentos.')
        self.summary.set(desc+'\n'+str(len(self.filtered))+' episódios no filtro. Processo observado: encerrado; nenhum problema em execução.\nOrçamento restante e memória por episódio aparecem no replay.')
        self.shown_skills=[s for s in self.skills if self.matches(s)]
        for i,s in enumerate(self.shown_skills):
            expr=freeze(s['expression']); used=[]
            for _,r in self.filtered:
                if r['seed']==s['seed'] and r['mode']==s['mode'] and r['agent']==s['agent'] and (r['step']>s['experience'] or r['step']==s['experience'] and r['phase']=='evaluation') and expr in set(subs(r['expression'])): used.append(r)
            self.memory.insert('','end',iid=str(i),values=(s['agent'],s['seed'],'treino '+str(s['experience']),depth(expr),text(expr),len(used),sum(r['success'] for r in used)))
        self.groups=[]
        for a in 'ABC':
            for st in (0,10,25,50,75,100):
                rs=[r for r in self.rows if self.matches(r,False) and r['agent']==a and r['phase']=='evaluation' and r['step']==st]
                if not rs: continue
                mean=lambda k:statistics.mean(r[k] for r in rs)
                self.groups.append((a,st,100*mean('success')))
                self.comparison.insert('','end',values=(a,st,len(rs),round(100*mean('success'),2),round(1000*mean('seconds'),2),round(mean('hypotheses'),1),round(mean('skills'),1),round(mean('peak_bytes')/1024,1)))
        self.draw_chart()
        if self.filtered: self.episodes.selection_set(str(self.filtered[0][0])); self.select_episode()
    def select_episode(self):
        selection=self.episodes.selection()
        if not selection:return
        self.current=self.rows[int(selection[0])]; r=self.current; self.playing=False
        self.events=self.all_events.get(r['index'],[]) if self.all_events else []
        if not self.events:
            self.events=[dict(kind='historical_observation',x=x,y=y,note='Ordem das observações registrada; sem timestamps por consulta.') for x,y in r['observations']]
            self.events.append(dict(kind='historical_result',expression=r['expression'],success=r['success'],note='Resumo histórico; sequência de busca indisponível.'))
        self.episode_label.set(f"Agente {r['agent']} · problema {r['index']} · {r['phase']} · checkpoint {r['step']} · "+('Eventos reais de nova execução' if self.all_events else 'Replay parcial do histórico'))
        self.slider.configure(to=max(0,len(self.events)-1)); self.slider.set(0); self.seek('0')
    def seek(self,v):
        if not self.events:return
        self.pos=int(float(v)); e=self.events[self.pos]; r=self.current
        consumed=next((x['consumed'] for x in reversed(self.events[:self.pos+1]) if 'consumed' in x),None)
        remaining=(str(max(0,2000-consumed)) if consumed is not None else 'não registrado neste ponto')
        self.details.configure(state='normal'); self.details.delete('1.0','end')
        self.details.insert('end',f"Evento {self.pos+1}/{len(self.events)} · orçamento restante: {remaining}\nMemória no início do episódio: {r['skills']}\n"+json.dumps(e,indent=2,ensure_ascii=False)); self.details.configure(state='disabled')
        expr=next((x.get('expression') for x in reversed(self.events[:self.pos+1]) if x.get('expression')),None); self.draw_tree(expr)
    def step(self,d): self.slider.set(max(0,min(len(self.events)-1,self.pos+d)))
    def toggle(self): self.playing=not self.playing
    def poll(self):
        try:
            while True:
                kind,msg=self.q.get_nowait()
                self.status.set(str(msg))
                if kind=='done': self.diag.configure(state='normal'); self.rescan()
                if kind=='error': self.diag.configure(state='normal'); messagebox.showerror('Diagnóstico',str(msg))
        except queue.Empty: pass
        if self.playing:
            if self.pos>=len(self.events)-1:self.playing=False
            else:self.step(1)
        self.root.after(200,self.poll)
    def draw_tree(self,e):
        self.tree.delete('all')
        if not e:return
        w=max(700,self.tree.winfo_width())
        def node(e,x,y,span):
            if e[0]<=3:
                for child,cx in [(e[1],x-span),(e[2],x+span)]:
                    self.tree.create_line(x,y,cx,y+52,fill='#8899aa'); node(child,cx,y+52,span/2)
            self.tree.create_oval(x-19,y-16,x+19,y+16,fill='#173e59',outline='')
            self.tree.create_text(x,y,text=text(e) if e[0]>3 else {1:'+',2:'−',3:'×'}[e[0]],fill='white')
        node(e,w/2,26,w/4); self.tree.create_text(10,230,anchor='w',text=text(e))
    def draw_chart(self):
        if not hasattr(self,'groups'):return
        c=self.chart;c.delete('all'); w=max(600,c.winfo_width()); left=50; width=w-90
        for y in range(0,101,25):
            py=200-y*1.6;c.create_line(left,py,w-25,py,fill='#e2e8ee');c.create_text(25,py,text=str(y)+'%')
        for st in (0,10,25,50,75,100): c.create_text(left+st/100*width,218,text=str(st))
        for a,color in [('A','#777777'),('B','#007e87'),('C','#b05c14')]:
            points=[(left+st/100*width,200-rate*1.6) for agent,st,rate in self.groups if agent==a]
            if len(points)>1:c.create_line(*[n for p in points for n in p],fill=color,width=3)
            c.create_text(100+'ABC'.index(a)*100,15,text='Agente '+a,fill=color)
        c.create_text(w-200,15,text='Sucesso por checkpoint · avaliação')
    def select_skill(self):
        ids=self.memory.selection()
        if not ids:return
        s=self.shown_skills[int(ids[0])]; components=set(subs(s['expression'])); own=freeze(s['expression'])
        related=[text(t['expression']) for t in self.shown_skills if t['seed']==s['seed'] and t['agent']==s['agent'] and freeze(t['expression']) in components and freeze(t['expression'])!=own]
        self.relation.set('Relações sintáticas (componentes armazenados): '+('; '.join(related) or 'nenhuma')+'. Não implica dependência causal ou ordem de descoberta.')
    def diagnose(self):
        self.diag.configure(state='disabled')
        def worker():
            try:
                from diagnostic import run
                path=run(lambda s:self.q.put(('progress',s))); self.q.put(('done','Diagnóstico salvo: '+str(path)))
            except Exception as ex:self.q.put(('error',str(ex)))
        threading.Thread(target=worker,daemon=True).start()

if __name__=='__main__':
    root=tk.Tk(); Panel(root); root.mainloop()
