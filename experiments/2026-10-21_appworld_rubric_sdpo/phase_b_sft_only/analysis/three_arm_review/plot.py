"""Standalone CPU plots for the final three-arm report."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager
fontManager.addfont('/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf')
O=Path(__file__).resolve().parent
s=json.loads((O/'summary.json').read_text());d=json.loads((O/'details_summary.json').read_text())
font=FontProperties(fname='/usr/share/fonts/truetype/arphic-gbsn00lp/gbsn00lp.ttf')
plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','axes.facecolor':'white','pdf.fonttype':42})
colors={'mixed':'#C58022','sdpo':'#BB4556','sft':'#15836C'}
labels={'mixed':'SFT + SDPO','sdpo':'仅 SDPO','sft':'仅 ZeroFail3 SFT'}
fig,axs=plt.subplots(2,3,figsize=(15,9.2))
metrics=[('整题成功数 / 57',lambda a,e:s[a]['dev'][str(e)]['successes'],(0,15),'d'),('平均检查通过率（%）',lambda a,e:100*s[a]['dev'][str(e)]['macro_test_pass_fraction'],(0,70),'.1f'),('重复文档步占比（%）',lambda a,e:100*s[a]['dev'][str(e)]['repeated_docs_fraction'],(0,105),'.1f'),('连续至少 5 次相同文档的题数 / 57',lambda a,e:s[a]['dev'][str(e)]['trajectories_with_5_consecutive_identical_docs'],(0,65),'d'),('含业务 API 代码的步骤数',lambda a,e:d['groups'][a][str(e)]['business_code_steps'],(0,630),'d')]
for ax,(title,fn,ylim,fmt) in zip(axs.flat,metrics):
 for a in labels:
  vals=[fn(a,e) for e in (1,2)]
  ax.plot([1,2],vals,marker='o',lw=2.5,color=colors[a],label=labels[a])
  for ep,v in zip((1,2),vals):
   offset=(0,8)
   if a=='sdpo' and ep==2:offset=(16,8) if v==0 else (0,-13)
   ax.annotate(format(v,fmt),(ep,v),xytext=offset,textcoords='offset points',ha='center',color=colors[a],fontsize=10)
 ax.set_title(title,pad=15);ax.set_xticks([1,2],['第 1 轮','第 2 轮']);ax.set_xlim(.75,2.25);ax.set_ylim(*ylim);ax.grid(axis='y',alpha=.18)
ax=axs.flat[5];bottom=[0,0,0]
for key,name,color in [('training_seconds','训练程序','#4D6E92'),('judge_wall_seconds','Codex 评审','#8AA3B5'),('evaluation_wall_seconds','dev 评估','#BCCAD1'),('other_wall_seconds','采样与其他','#E0E6E9')]:
 vals=[s[a]['timing'][key]/3600 for a in labels];ax.bar(range(3),vals,bottom=bottom,label=name,color=color);bottom=[x+y for x,y in zip(bottom,vals)]
for i,v in enumerate(bottom):ax.text(i,v+.35,f'{v:.2f} h',ha='center',fontsize=10)
ax.set_xticks(range(3),['混合','纯 SDPO','纯 SFT']);ax.set_ylim(0,30);ax.set_title('全流程耗时（小时）',pad=15);ax.legend(fontsize=9,loc='upper right');ax.grid(axis='y',alpha=.18)
handles,ls=axs.flat[0].get_legend_handles_labels();fig.legend(handles,ls,loc='upper center',bbox_to_anchor=(.5,.94),ncol=3,frameon=False)
fig.suptitle('AppWorld dev57：两种含 SDPO 的组退化，纯 ZeroFail3 SFT 改善',fontsize=19,y=.99)
fig.text(.5,.015,'同一 dev57、单种子、两轮在线训练；业务 API 口径排除文档、Supervisor 和登录，代码出现不保证调用成功。',ha='center',fontsize=10,color='#555555')
fig.tight_layout(rect=(0,.045,1,.9),h_pad=2.8,w_pad=2.4)
fig.savefig(O/'three_arm_overview.png',dpi=180,bbox_inches='tight');fig.savefig(O/'three_arm_overview.pdf',bbox_inches='tight');plt.close(fig)
print(O/'three_arm_overview.png')
