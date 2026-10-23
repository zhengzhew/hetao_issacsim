"""Simple Windows leader connector: choose a calibration once, then connect."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from serial.tools import list_ports
from arm_devices import DEFAULT_SAMPLE_RATE
from connector_config import ConnectorConfig, choose_port, friendly_error, state_directory

ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]


def ports():
    return [{'port':p.device,'description':p.description,'serial':p.serial_number,'vid':p.vid,'pid':p.pid} for p in list_ports.comports()]


def worker():
    log=Path(sys.argv[2]);sys.stdout=sys.stderr=log.open('a',encoding='utf-8',buffering=1)
    sys.argv=[sys.argv[0]]+sys.argv[3:]
    try:
        import leader_client
        leader_client.main()
    except Exception as error:
        print(json.dumps({'event':'failed','message':friendly_error(error)},ensure_ascii=False),flush=True)
        traceback.print_exc();raise SystemExit(1)


class ConnectorWindow:
    def __init__(self,root,config=None,enumerate_ports=ports,spawn=subprocess.Popen):
        import tkinter as tk
        from tkinter import ttk
        self.root=root;self.store=config or ConnectorConfig(ROOT,downloads=Path.home()/'Downloads')
        self.enumerate_ports=enumerate_ports;self.spawn=spawn;self.process=None;self.closing=False
        self.offset=0;self.partial='';self.failure='';self.available=[];self.manual_port=None
        self.settings_open=False;self.log_open=False;self.log_path=None;self.stop_path=None
        root.title(f'SO-101 连接工具 V6 · {DEFAULT_SAMPLE_RATE} Hz · 配对码连接');root.geometry('720x700');root.minsize(640,630)
        style=ttk.Style(root);style.configure('TButton',padding=(14,9));style.configure('TLabel',font=('Microsoft YaHei UI',10));style.configure('Connect.TButton',font=('Microsoft YaHei UI',13,'bold'),padding=16)
        self.frame=ttk.Frame(root,padding=22);self.frame.pack(fill='both',expand=True)
        ttk.Label(self.frame,text='填写服务器地址，连接机械臂',font=('Microsoft YaHei UI',17,'bold')).pack(anchor='w')
        ttk.Label(self.frame,text='填写服务器地址和采集器配对码，再选择这台机械臂的配置。').pack(anchor='w',pady=(8,18))
        self.server=tk.StringVar(value=self.store.data['server']);self.calibration=tk.StringVar(value=self.store.data.get('calibration',''))
        self.selection=tk.StringVar();self.pair_code=tk.StringVar();self.station_id=tk.StringVar(value=self.store.data.get('stationId',''));self.station_selection=tk.StringVar();self.station_choices=self.store.data.get('stations',[]);self.status=tk.StringVar(value=self.store.notice or '准备连接')
        self.port_text=tk.StringVar();self.file_text=tk.StringVar();self.summary=tk.StringVar()
        self.profile_selection=tk.StringVar();self.profile_ids=[]
        server_card=ttk.LabelFrame(self.frame,text='服务器地址',padding=12);server_card.pack(fill='x',pady=(0,12))
        server_row=ttk.Frame(server_card);server_row.pack(fill='x')
        self.server_box=ttk.Entry(server_row,textvariable=self.server);self.server_box.pack(side='left',fill='x',expand=True)
        self.save_server_button=ttk.Button(server_row,text='保存地址',command=self.save_server);self.save_server_button.pack(side='right',padx=(12,0))
        self.server_box.bind('<Return>',lambda event:self.save_server())
        ttk.Label(server_card,text='填写实际服务器地址（含 http:// 或 https:// 和端口），保存后下次自动恢复。',wraplength=620).pack(anchor='w',pady=(6,0))
        self.pair_row=ttk.Frame(server_card)
        ttk.Label(self.pair_row,text='采集器配对码（教师端生成，不是浏览器配对码）',wraplength=620).pack(anchor='w')
        self.pair_box=ttk.Entry(self.pair_row,textvariable=self.pair_code);self.pair_box.pack(fill='x',pady=4)
        ttk.Label(self.pair_row,text='首次连接或凭证过期时填写；有效配对会自动记住。',wraplength=620).pack(anchor='w')
        self.pair_row.pack(fill='x',pady=(10,0))
        card=ttk.LabelFrame(self.frame,text='当前机械臂配置',padding=12);card.pack(fill='x')
        file_row=ttk.Frame(card);file_row.pack(fill='x')
        self.profile_box=ttk.Combobox(file_row,textvariable=self.profile_selection,state='readonly');self.profile_box.pack(side='left',fill='x',expand=True);self.profile_box.bind('<<ComboboxSelected>>',self.select_saved_profile)
        self.file_button=ttk.Button(file_row,text='添加配置',command=self.select_file);self.file_button.pack(side='right',padx=(12,0))
        ttk.Label(card,textvariable=self.file_text,wraplength=620).pack(anchor='w',pady=(8,0))
        row=ttk.Frame(self.frame);row.pack(fill='x',pady=(12,4))
        ttk.Label(row,textvariable=self.port_text).pack(side='left',fill='x',expand=True)
        self.refresh_button=ttk.Button(row,text='重新检测',command=self.refresh_ports);self.refresh_button.pack(side='right')
        ttk.Label(self.frame,textvariable=self.summary,wraplength=650,foreground='#567a65').pack(anchor='w',pady=(2,12))
        controls=ttk.Frame(self.frame);controls.pack(fill='x')
        self.connect_button=ttk.Button(controls,text='连接机械臂',style='Connect.TButton',command=self.connect);self.connect_button.pack(side='left',fill='x',expand=True)
        self.stop_button=ttk.Button(controls,text='停止同步',command=self.stop,state='disabled');self.stop_button.pack(side='left',padx=(12,0))
        ttk.Label(self.frame,textvariable=self.status,wraplength=650).pack(anchor='w',pady=14)
        links=ttk.Frame(self.frame);links.pack(fill='x')
        self.settings_button=ttk.Button(links,text='连接设置',command=self.toggle_settings);self.settings_button.pack(side='left')
        ttk.Button(links,text='查看日志',command=self.toggle_log).pack(side='left',padx=(10,0))
        self.details=ttk.Frame(self.frame,padding=(0,12,0,0))
        ttk.Label(self.details,text='USB 串口（检测到多个设备时选择）').grid(row=2,column=0,sticky='w')
        self.port_box=ttk.Combobox(self.details,textvariable=self.selection,state='readonly');self.port_box.grid(row=3,column=0,columnspan=2,sticky='ew',pady=(4,10));self.port_box.bind('<<ComboboxSelected>>',self.select_port)
        self.station_row=ttk.Frame(self.details)
        ttk.Label(self.station_row,text='连接哪一个体验台（选一次即可）').pack(anchor='w')
        self.station_box=ttk.Combobox(self.station_row,textvariable=self.station_selection,state='readonly');self.station_box.pack(fill='x',pady=4);self.station_box.bind('<<ComboboxSelected>>',self.select_station)
        self.update_stations(self.station_choices,self.station_id.get())
        self.details.columnconfigure(0,weight=1)
        self.log_box=tk.Text(self.frame,height=8,wrap='word',font=('Consolas',9),state='disabled')
        self.refresh_ports();self.update_summary();root.protocol('WM_DELETE_WINDOW',self.close)
        self.fit_window()
        self.timer=root.after(250,self.poll)

    def update_summary(self):
        profiles=self.store.profiles();labels=[];names=[p['calibrationName'] for p in profiles]
        self.profile_ids=[p.get('profileKey',p['calibrationHash']) for p in profiles]
        for index,profile in enumerate(profiles):
            label=profile['calibrationName']
            if names.count(label)>1:label+=' · '+Path(profile['sourceCalibration']).parent.name
            if label in labels:label+=' ('+str(index+1)+')'
            labels.append(label)
        self.profile_box['values']=labels
        active=self.store.data.get('activeProfile')
        if active in self.profile_ids and self.calibration.get():self.profile_box.current(self.profile_ids.index(active))
        else:self.profile_selection.set('')
        source=self.store.data.get('sourceCalibration') or self.calibration.get()
        self.file_text.set('文件：'+source if self.calibration.get() else '请添加或选择当前机械臂的配置文件')
        from arm_devices import DRIVERS
        driver=DRIVERS.get(self.store.data.get('driver'),{}).get('name','请选择机械臂配置')
        self.summary.set('驱动：'+driver+'。更换服务器后请使用对应的采集器配对码。')

    def save_server(self,show_status=True):
        if self.process:return False
        try:
            previous=self.store.data.get('server')
            saved=self.store.remember_server(self.server.get())
            self.server.set(saved['server'])
            if saved['server']!=previous:self.update_stations([], '')
            if show_status:self.status.set('服务器地址已保存：'+saved['server'])
            return True
        except Exception as error:
            self.status.set(friendly_error(error));self.server_box.focus_set();return False

    def select_file(self):
        if self.process:return
        if not self.save_server(show_status=False):return
        from tkinter import filedialog
        file=filedialog.askopenfilename(title='添加这台机械臂的配置文件',filetypes=[('机械臂配置包','*.robot.json'),('校准 JSON','*.json')])
        if file:
            try:
                saved=self.store.save(self.server.get(),file)
                self.calibration.set(saved['calibration']);self.refresh_ports();self.update_summary()
                self.status.set('当前配置：'+saved['calibrationName']+'，点击“连接机械臂”')
            except Exception as error:self.status.set(friendly_error(error))

    def select_saved_profile(self,event=None):
        if self.process:self.update_summary();return
        index=self.profile_box.current()
        if index<0:return
        try:
            saved=self.store.select_profile(self.profile_ids[index])
            self.calibration.set(saved['calibration']);self.refresh_ports();self.update_summary()
            self.status.set('已切换到 '+saved['calibrationName']+'，点击“连接机械臂”')
        except Exception as error:
            self.update_summary();self.status.set(friendly_error(error))

    def refresh_ports(self):
        if self.process:return
        self.available=self.enumerate_ports();self.manual_port=None
        expected=self.store.data.get('expectedLeaderSerial','')
        remembered=choose_port(self.available,self.store.data.get('portIdentity'),expected)
        self.port_box['values']=[p['port']+' · '+p['description'] for p in self.available]
        if remembered:self.port_box.current(self.available.index(remembered));self.manual_port=remembered
        else:self.selection.set('')
        self.port_text.set('已找到主臂 '+remembered['port'] if remembered else
                           ('未找到此配置包的主臂，请插好 USB 后重新检测' if expected else
                            '请插入 USB；多个设备时在“连接设置”中选串口'))

    def select_port(self,event=None):
        index=self.port_box.current()
        self.manual_port=self.available[index] if index>=0 else None
        if self.manual_port:self.port_text.set('已选择 '+self.manual_port['port'])

    def fit_window(self):
        self.root.update_idletasks()
        height=max(630,self.frame.winfo_reqheight()+12)
        self.root.minsize(640,height);self.root.geometry('720x'+str(height))

    def toggle_settings(self,force=None):
        self.settings_open=not self.settings_open if force is None else force
        if self.settings_open:self.details.pack(fill='x')
        else:self.details.pack_forget()
        self.settings_button.configure(text='收起设置' if self.settings_open else '连接设置')
        self.fit_window()

    def toggle_log(self):
        self.log_open=not self.log_open
        if self.log_open:self.log_box.pack(fill='both',expand=True,pady=(10,0))
        else:self.log_box.pack_forget()
        self.fit_window()

    def append(self,text):
        self.log_box.configure(state='normal');self.log_box.insert('end',text+'\n');self.log_box.see('end');self.log_box.configure(state='disabled')

    def set_running(self,running):
        for widget in (self.connect_button,self.file_button,self.refresh_button,self.server_box,self.save_server_button,self.pair_box):widget.configure(state='disabled' if running else 'normal')
        self.profile_box.configure(state='disabled' if running else 'readonly');self.station_box.configure(state='disabled' if running else 'readonly');self.port_box.configure(state='disabled' if running else 'readonly');self.stop_button.configure(state='normal' if running else 'disabled')

    def connect(self):
        if self.process:return
        if not self.save_server(show_status=False):return
        if not self.calibration.get():self.select_file()
        if not self.calibration.get():return
        # Enumeration is read-only; never open candidate ports to guess protocols.
        current=self.enumerate_ports()
        if self.manual_port not in current:
            self.refresh_ports()
        if not self.manual_port:
            if self.store.data.get('expectedLeaderSerial'):
                self.status.set('未找到此配置包的主臂，请插好 USB 后点击“重新检测”')
            else:
                self.status.set('没有找到对应 USB 串口，请插好机械臂或在下方选择串口');self.toggle_settings(True)
            return
        try:
            self.store.data['stationId']=self.station_id.get()
            saved=self.store.save(self.server.get(),self.calibration.get(),self.manual_port)
            data=self.store.directory/'logs';data.mkdir(parents=True,exist_ok=True)
            stamp=str(time.time_ns());self.stop_path=data/(stamp+'.stop');self.log_path=data/(stamp+'.log');self.log_path.touch()
            self.offset=0;self.partial='';self.failure=''
            command=[sys.executable]
            if not getattr(sys,'frozen',False):command.append(str(Path(__file__).resolve()))
            command+=['--worker',str(self.log_path),'--port',self.manual_port['port'],'--server',saved['server'],'--calibration',saved['calibration'],'--arm-id',saved['armId'],'--driver',saved['driver'],'--state-dir',str(self.store.directory),'--stop-file',str(self.stop_path)]
            command+=['--rate',str(DEFAULT_SAMPLE_RATE)]
            if self.station_id.get():command+=['--station-id',self.station_id.get()]
            if self.pair_code.get().strip():command+=['--pair-code',self.pair_code.get().strip()]
            self.process=self.spawn(command,cwd=ROOT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.pair_code.set('');self.server.set(saved['server']);self.update_summary();self.set_running(True)
            self.status.set('正在连接…');self.append('使用配置：'+saved['calibrationName']+' → '+saved['server'])
        except Exception as error:self.status.set(friendly_error(error));self.append(str(error))

    def update_stations(self,stations,selected=''):
        self.station_choices=stations
        self.station_box['values']=[s['name']+' · '+s['id'] for s in stations]
        self.station_selection.set('');self.station_id.set(selected)
        for index,station in enumerate(stations):
            if station['id']==selected:self.station_box.current(index)
        if len(stations)>1:self.station_row.grid(row=4,column=0,columnspan=2,sticky='ew')
        else:self.station_row.grid_remove()

    def select_station(self,event=None):
        index=self.station_box.current()
        if index>=0:self.station_id.set(self.station_choices[index]['id'])

    def consume_event(self,event):
        kind=event.get('event')
        if kind=='authorized':
            stations=event.get('stations',[]);station=event['stationId'];self.update_stations(stations,station);self.store.remember_station(station,stations)
        elif kind=='station-required':
            self.update_stations(event['stations']);self.station_row.grid(row=4,column=0,columnspan=2,sticky='ew');self.toggle_settings(True);self.failure=event['message'];self.status.set(self.failure)
        elif kind=='following':self.status.set('正在同步 · '+str(event.get('rate_hz',0))+' 次/秒')
        elif kind=='serial-ready':self.status.set('已找到机械臂，等待仿真关卡…')
        elif kind=='scene-reconnected':self.status.set('已连接，可以移动实物机械臂')
        elif kind=='waiting':self.status.set('请在浏览器选择机械臂关卡，选好后会自动同步')
        elif kind=='reconnecting':self.status.set('连接中断，正在自动重连…')
        elif kind=='failed':self.failure=event.get('message','连接失败');self.status.set(self.failure)
        elif kind=='pairing-required':
            self.failure=event.get('message','服务器需要配对码');self.status.set(self.failure);self.pair_box.focus_set();self.fit_window()
        if kind!='following':self.append(json.dumps(event,ensure_ascii=False))

    def poll(self):
        if self.process:
            if self.log_path.exists():
                with self.log_path.open('r',encoding='utf-8',errors='replace') as stream:
                    stream.seek(self.offset);chunk=stream.read();self.offset=stream.tell()
                text=self.partial+chunk;lines=text.split('\n');self.partial=lines.pop()
                for line in lines:
                    if not line:continue
                    try:self.consume_event(json.loads(line))
                    except (ValueError,TypeError):self.append(line)
            code=self.process.poll()
            if code is not None:
                self.process=None;self.set_running(False)
                if not self.failure:self.status.set('已停止，下次直接点击连接' if code==0 else '连接中断，请查看日志或修改连接设置')
        if self.closing and not self.process:self.root.destroy();return
        self.timer=self.root.after(250,self.poll)

    def stop(self):
        if self.process and self.process.poll() is None:
            self.stop_path.touch();self.status.set('正在停止并释放串口…');self.stop_button.configure(state='disabled')

    def close(self):
        self.closing=True;self.stop()
        if not self.process:self.root.after_cancel(self.timer);self.root.destroy()


def gui(smoke_path=None):
    import tkinter as tk
    root=tk.Tk()
    if smoke_path:root.withdraw()
    try:window=ConnectorWindow(root)
    except Exception as error:
        if smoke_path:raise
        from tkinter import messagebox
        messagebox.showerror('连接配置无法读取',str(error));root.destroy();return
    if smoke_path:
        import ssl
        from connector_tls import ssl_context
        context=ssl_context('https://10.72.255.16')
        assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        root.update_idletasks();Path(smoke_path).write_text(json.dumps({'title':root.title(),'server':window.server.get(),'calibration':window.calibration.get(),'port':window.manual_port,'settingsOpen':window.settings_open,'profileName':window.store.data.get('calibrationName'),'profiles':window.profile_box['values'],'activeProfile':window.store.data.get('activeProfile'),'autoConnect':window.store.data.get('autoConnect',False),'driver':window.store.data.get('driver'),'pairCodeOnMainWindow':window.pair_row.winfo_manager()=='pack' and window.pair_row.master is not window.details,'bundledCaLoaded':True},ensure_ascii=False),encoding='utf-8');window.close();return
    root.mainloop()

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':worker()
    else:gui(sys.argv[2] if len(sys.argv)>2 and sys.argv[1]=='--ui-smoke' else None)
