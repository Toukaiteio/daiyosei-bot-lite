"""
ModelScope AI 图片生成工具
使用 Playwright 自动化操作 ModelScope 的图片生成页面
"""

import asyncio
import json
import os
import platform
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import logging

logger = logging.getLogger(__name__)


class ModelScopeImageGenerator:
    """ModelScope AI 图片生成器"""
    
    def __init__(self, headless: bool = True, mode: str = "text_to_image"):
        """
        初始化图片生成器
        
        Args:
            headless: 是否使用无头模式
            mode: 模式，"text_to_image" (文生图) 或 "image_edit" (图像编辑)
        """
        self.headless = headless
        self.mode = mode
        self.url = "https://www.modelscope.cn/aigc/imageGeneration"
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Cookie 和 LocalStorage 配置
        self.cookies = [
             # ... (Keep existing cookies)
{
                "name": "csrf_session",
                "value": "MTc2NDU3NDc3MXxEWDhFQVFMX2dBQUJFQUVRQUFBeV80QUFBUVp6ZEhKcGJtY01DZ0FJWTNOeVpsTmhiSFFHYzNSeWFXNW5EQklBRUVKdlpYZHFhRmRTYUhSTlRHcEVaelE9fIFuz_sVJ209oILRDkR2OFdMkAXRbjWyv_1fjB-N7axo",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "csrf_token",
                "value": "zE03CdZBcDbs0G9YRz7Xsn2jJ1Q%3D",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "t",
                "value": "9b6b297fbf9b383368e54ebf1fb059c6",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "m_session_id",
                "value": "51ad089f-909c-4ee3-aba0-5b308c8c159b",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "h_uid",
                "value": "2220469301704",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "acw_tc",
                "value": "0b62601217661324172712085e8e2ebba24dd7f7593ed4e042870fcb2bda02",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "ssxmod_itna",
                "value": "1-iqGOYK0IeRxUxWqD5i75KPQKezCDRDeqAQDXDUkQe7UNGcD8xiKDHDIh/DSLnkg0Ijt93BAm2qDBTHoDSxD=7DK4GTpG=i4hzoCiATvpRC0BiNKRYjmG9mQm00=ekoaL/bSc62syGZSpYToDCPDExGkxcwGDeeaDCeDQxirDD4DAiPDFxibDievQ4DdaUgvhFgwwDGrDlKDRp2Ya4GWDiPD7aE=srip9F7prbxD0xD16bCfDDPDahoxDG5xWTGiQbDDEWEvP/SYO7j=zz0xa4G1LD0HiAUXeXzMeifvwHz9oZ7L640OD09jBnhRD=0mEDPwRFGKibm2D32Fmhe3xeF_=tDC3G=b0qp2xYi4GDqK0D8iozGFjhqmGOQuFCOoFKevgFii43h/S5DLmDo7oIAemi1Kf13h3pr4/b4mDOSrNC0N447GDbEYq7D51GieWeOGDD",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "ssxmod_itna2",
                "value": "1-iqGOYK0IeRxUxWqD5i75KPQKezCDRDeqAQDXDUkQe7UNGcD8xiKDHDIh/DSLnkg0Ijt93BAmrDia_iEp=1Rmghzt/Pjq5OoGRpGD",
                "domain": ".modelscope.cn",
                "path": "/"
            },
            {
                "name": "isg",
                "value": "BI2NyJTR2CmwbXxoecQQ4yfgnKkHasE8Tkp7Fc8VHyRAxq54l7uuDG9AM1qgYtn0",
                "domain": ".modelscope.cn",
                "path": "/"
            }
        ]
        
        self.local_storage = {
            "APLUS_LS_KEY": "[\"APLUS_S_CORE_1.0.19_20251202143226_36879916\"]",
            "msLoginPromptTime": "1766218839557",
            "__00b204e9800998__": "4041669758a19ac5517dbe||1779799043522",
            "isg__": "BCcnHQIXAntO3Yaar8Ia0emOtlvxrPuOUFQhB_mSarfR6EWqAXzT31CqC-j2ZNMG",
            "msShowNewMedalTip": "true",
            "msAigcPictureTour": "true",
            "maas_user": "Daiyosei",
            "msUserName": "Daiyosei",
            "local": "zh_CN"
        }
        
        self.local_storage["APLUS_S_CORE_1.0.19_20251202143226_36879916"] = """/*! 2024-09-10 16:39:26 v8.15.24 */
!function(e){function i(n){if(o[n])return o[n].exports;var r=o[n]={exports:{},id:n,loaded:!1};return e[n].call(r.exports,r,r.exports,i),r.loaded=!0,r.exports}var o={};return i.m=e,i.c=o,i.p="",i(0)}([function(e,i){"use strict";var o=window,n=document;!function(){var e=2,r="ali_analytics";if(o[r]&&o[r].ua&&e<=o[r].ua.version)return void(i.info=o[r].ua);var t,a,d,s,c,u,h,l,m,b,f,v,p,w,g,x,z,O=o.navigator,k=O.appVersion,T=O&&O.userAgent||"",y=function(e){var i=0;return parseFloat(e.replace(/\\./g,function(){return 0===i++?".":""}))},_=function(e,i){var o,n;i[o="trident"]=.1,(n=e.match(/Trident\\/([\\d.]*)/))&&n[1]&&(i[o]=y(n[1])),i.core=o},N=function(e){var i,o;return(i=e.match(/MSIE ([^;]*)|Trident.*; rv(?:\\s|:)?([0-9.]+)/))&&(o=i[1]||i[2])?y(o):0},P=function(e){return e||"other"},M=function(e){function i(){for(var i=[["Windows NT 5.1","winXP"],["Windows NT 6.1","win7"],["Windows NT 6.0","winVista"],["Windows NT 6.2","win8"],["Windows NT 10.0","win10"],["iPad","ios"],["iPhone;","ios"],["iPod","ios"],["Macintosh","mac"],["Android","android"],["Ubuntu","ubuntu"],["Linux","linux"],["Windows NT 5.2","win2003"],["Windows NT 5.0","win2000"],["Windows","winOther"],["rhino","rhino"]],o=0,n=i.length;o<n;++o)if(e.indexOf(i[o][0])!==-1)return i[o][1];return"other"}function r(e,i,n,r){var t,a=o.navigator.mimeTypes;try{for(t in a)if(a.hasOwnProperty(t)&&a[t][e]==i){if(void 0!==n&&r.test(a[t][n]))return!0;if(void 0===n)return!0}return!1}catch(e){return!1}}var t,a,d,s,c,u,h,l="",m=l,b=l,f=[6,9],v="{{version}}",p="<!--[if IE "+v+"]><s></s><![endif]-->",w=n&&n.createElement("div"),g=[],x={webkit:void 0,edge:void 0,trident:void 0,gecko:void 0,presto:void 0,chrome:void 0,safari:void 0,firefox:void 0,ie:void 0,ieMode:void 0,opera:void 0,mobile:void 0,core:void 0,shell:void 0,phantomjs:void 0,os:void 0,ipad:void 0,iphone:void 0,ipod:void 0,ios:void 0,android:void 0,nodejs:void 0,extraName:void 0,extraVersion:void 0};if(w&&w.getElementsByTagName&&(w.innerHTML=p.replace(v,""),g=w.getElementsByTagName("s")),g.length>0){for(_(e,x),s=f[0],c=f[1];s<=c;s++)if(w.innerHTML=p.replace(v,s),g.length>0){x[b="ie"]=s;break}!x.ie&&(d=N(e))&&(x[b="ie"]=d)}else((a=e.match(/AppleWebKit\\/*\\s*([\\d.]*)/i))||(a=e.match(/Safari\\/([\\d.]*)/)))&&a[1]?(x[m="webkit"]=y(a[1]),(a=e.match(/OPR\\/(\\d+\\.\\d+)/))&&a[1]?x[b="opera"]=y(a[1]):(a=e.match(/Chrome\\/([\\d.]*)/))&&a[1]?x[b="chrome"]=y(a[1]):(a=e.match(/\\/([\\d.]*) Safari/))&&a[1]?x[b="safari"]=y(a[1]):x.safari=x.webkit,(a=e.match(/Edge\\/([\\d.]*)/))&&a[1]&&(m=b="edge",x[m]=y(a[1])),/ Mobile\\//.test(e)&&e.match(/iPad|iPod|iPhone/)?(x.mobile="apple",a=e.match(/OS ([^\\s]*)/),a&&a[1]&&(x.ios=y(a[1].replace("_","."))),t="ios",a=e.match(/iPad|iPod|iPhone/),a&&a[0]&&(x[a[0].toLowerCase()]=x.ios)):/ Android/i.test(e)?(/Mobile/.test(e)&&(t=x.mobile="android"),a=e.match(/Android ([^\\s]*);/),a&&a[1]&&(x.android=y(a[1]))):(a=e.match(/NokiaN[^\\/]*|Android \\d\\.\\d|webOS\\/\\d\\.\\d/))&&(x.mobile=a[0].toLowerCase()),(a=e.match(/PhantomJS\\/([^\\s]*)/))&&a[1]&&(x.phantomjs=y(a[1]))):(a=e.match(/Presto\\/([\\d.]*)/))&&a[1]?(x[m="presto"]=y(a[1]),(a=e.match(/Opera\\/([\\d.]*)/))&&a[1]&&(x[b="opera"]=y(a[1]),(a=e.match(/Opera\\/.* Version\\/([\\d.]*)/))&&a[1]&&(x[b]=y(a[1])),(a=e.match(/Opera Mini[^;]*/))&&a?x.mobile=a[0].toLowerCase():(a=e.match(/Opera Mobi[^;]*/))&&a&&(x.mobile=a[0]))):(d=N(e))?(x[b="ie"]=d,_(e,x)):(a=e.match(/Gecko/))&&(x[m="gecko"]=.1,(a=e.match(/rv:([\\d.]*)/))&&a[1]&&(x[m]=y(a[1]),/Mobile|Tablet/.test(e)&&(x.mobile="firefox")),(a=e.match(/Firefox\\/([\\d.]*)/))&&a[1]&&(x[b="firefox"]=y(a[1])));t||(t=i());var z,O,T;if(!r("type","application/vnd.chromium.remoting-viewer")){z="scoped"in n.createElement("style"),T="v8Locale"in o;try{O=o.external||void 0}catch(e){}if(a=e.match(/360SE/))u="360";else if((a=e.match(/SE\\s([\\d.]*)/))||O&&"SEVersion"in O)u="sougou",h=y(a[1])||.1;else if((a=e.match(/Maxthon(?:\\/)+([\\d.]*)/))&&O){u="maxthon";try{h=y(O.max_version||a[1])}catch(e){h=.1}}else z&&T?u="360se":z||T||!/Gecko\\)\\s+Chrome/.test(k)||x.opera||x.edge||(u="360ee")}(a=e.match(/TencentTraveler\\s([\\d.]*)|QQBrowser\\/([\\d.]*)/))?(u="tt",h=y(a[2])||.1):(a=e.match(/LBBROWSER/))||O&&"LiebaoGetVersion"in O?u="liebao":(a=e.match(/TheWorld/))?(u="theworld",h=3):(a=e.match(/TaoBrowser\\/([\\d.]*)/))?(u="taobao",h=y(a[1])||.1):(a=e.match(/UCBrowser\\/([\\d.]*)/))&&(u="uc",h=y(a[1])||.1),x.os=t,x.core=x.core||m,x.shell=b,x.ieMode=x.ie&&n.documentMode||x.ie,x.extraName=u,x.extraVersion=h;var P=o.screen.width,M=o.screen.height;return x.resolution=P+"x"+M,x},S=function(e){function i(e){return Object.prototype.toString.call(e)}function o(e,o,n){if("[object Function]"==i(o)&&(o=o(n)),!o)return null;var r={name:e,version:""},t=i(o);if(o===!0)return r;if("[object String]"===t){if(n.indexOf(o)!==-1)return r}else if(o.exec){var a=o.exec(n);if(a)return a.length>=2&&a[1]?r.version=a[1].replace(/_/g,".")"""
    
    async def initialize(self):
        """初始化浏览器"""
        playwright = await async_playwright().start()
        
        # 浏览器启动参数，增强服务器环境兼容性
        launch_args = {
            'headless': self.headless,
            'args': [
                '--disable-gpu',  # 禁用GPU加速
                '--no-sandbox',  # 禁用沙箱（在某些Linux服务器上必需）
                '--disable-dev-shm-usage',  # 避免共享内存问题
                '--disable-blink-features=AutomationControlled',  # 减少被检测为自动化
            ]
        }
        
        self.browser = await playwright.chromium.launch(**launch_args)
        self.context = await self.browser.new_context()
        
        # 设置 cookies
        await self.context.add_cookies(self.cookies)
        
        self.page = await self.context.new_page()
        
        # 访问页面 - 增加超时时间并添加重试机制
        max_retries = 3
        retry_delay = 5  # 秒
        
        for attempt in range(max_retries):
            try:
                logger.info(f"正在访问 ModelScope 页面... (尝试 {attempt + 1}/{max_retries})")
                # 设置更长的超时时间（60秒）以适应服务器环境
                await self.page.goto(self.url, timeout=60000, wait_until='domcontentloaded')
                logger.info("页面导航成功")
                break
            except Exception as goto_error:
                logger.error(f"页面导航失败 (尝试 {attempt + 1}/{max_retries}): {goto_error}")
                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error("页面导航多次失败，请检查:")
                    logger.error("  1. 服务器是否能访问 https://www.modelscope.cn")
                    logger.error("  2. 防火墙设置是否阻止了访问")
                    logger.error("  3. 网络代理配置是否正确")
                    raise Exception(f"无法访问 ModelScope 网站，已重试 {max_retries} 次: {goto_error}")
        
        # 设置 localStorage
        for key, value in self.local_storage.items():
            await self.page.evaluate(f"localStorage.setItem('{key}', {json.dumps(value)})")
        
        # 刷新页面以应用 localStorage - 同样增加超时时间
        logger.info("刷新页面以应用配置...")
        await self.page.reload(timeout=60000, wait_until='domcontentloaded')
        
        # 如果是文生图模式，点击切换模型
        if self.mode == "text_to_image":
            # 新增 steps: 点击 Z Image
            try:
                logger.info("正在寻找并点击 'Z Image' 样式卡片...")
                # 使用 Playwright 的 locator filter 功能定位包含 "Z Image" 的卡片
                # 目标结构: <div class="muse-style-card"><div class="footer">Z Image</div></div>
                z_image_card = self.page.locator('.muse-style-card').filter(has=self.page.locator('.footer', has_text='Z Image'))
                
                # 等待元素可见
                await z_image_card.wait_for(state='visible', timeout=10000)
                
                # 点击
                await z_image_card.click()
                logger.info("成功点击 'Z Image' 样式卡片")
                
                # 等待一小会儿确保生效
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.warning(f"点击 'Z Image' 样式卡片失败: {e}")
        else:
            logger.info("当前为 Image Edit 模式，跳过 'Z Image' 卡片点击")
        
        logger.info("浏览器初始化完成")
    
    async def close(self):
        """关闭浏览器"""
        try:
            if self.page:
                await self.page.close()
                await asyncio.sleep(0.1)  # 给一点时间让资源清理
            if self.context:
                await self.context.close()
                await asyncio.sleep(0.1)
            if self.browser:
                await self.browser.close()
                await asyncio.sleep(0.2)  # 等待浏览器进程完全退出
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.warning(f"关闭浏览器时出现警告（可忽略）: {e}")
    
    async def generate_image(self, prompt: str, image_paths: Optional[List[str]] = None, timeout: int = 60000) -> Optional[str]:
        """
        生成图片
        
        Args:
            prompt: 提示词
            image_paths: 可选，垫图路径列表（用于 Image Edit）
            timeout: 超时时间（毫秒）
            
        Returns:
            生成的图片 URL，失败返回 None
        """
        try:
            # 等待页面完全加载 - 增加超时时间以适应服务器环境
            # 先等待 load 状态，再尝试等待 networkidle
            try:
                await self.page.wait_for_load_state('load', timeout=20000)
                logger.info("页面基本加载完成")
                # 尝试等待 networkidle，如果超时也继续
                try:
                    await self.page.wait_for_load_state('networkidle', timeout=30000)
                    logger.info("页面网络请求已完成")
                except:
                    logger.warning("等待 networkidle 超时，但继续执行")
                    await asyncio.sleep(2)  # 给额外2秒时间
            except Exception as load_err:
                logger.error(f"页面加载超时: {load_err}")
                # 尝试截图诊断
                try:
                    await self.page.screenshot(path="load_timeout_error.png")
                    logger.info("已保存页面加载超时截图")
                except:
                    pass
                return None
            
            # 处理图片上传 (如果有)
            if image_paths and len(image_paths) > 0:
                logger.info(f"准备上传 {len(image_paths)} 张图片: {image_paths}")
                try:
                    # 点击上传区域触发文件选择 (弹出对话框)
                    upload_trigger_selector = '.muse-pic-upload-init'
                    
                    # 等待上传按钮可见
                    await self.page.wait_for_selector(upload_trigger_selector, state='visible', timeout=10000)
                    
                    # 点击触发上传对话框
                    await self.page.click(upload_trigger_selector)
                    logger.info("已点击上传触发按钮")

                    # 等待对话框出现 (.ant-modal-content)
                    await self.page.wait_for_selector('.ant-modal-content', state='visible', timeout=5000)
                    logger.info("上传对话框已弹出")
                    
                    # 选择"本地上传"
                    # 定位包含"本地上传"文本的label
                    local_upload_label = self.page.locator('label').filter(has_text='本地上传').first
                    await local_upload_label.wait_for(state='visible', timeout=5000)
                    await local_upload_label.click()
                    logger.info("已选择【本地上传】")

                    # 等待实际的上传 input 出现 (.ant-upload input[type='file'])
                    # 注意：Playwright 上传需要 set_files 到 input 元素
                    # 这里的结构是 <span class="ant-upload ..."><input type="file" ...></span>
                    file_input_selector = 'div.ant-modal-content input[type="file"]'
                    
                    # 监听文件选择器 (这一次点击的是"点击上传图片"区域，或者直接 set_files 如果 input 存在)
                    # 观察提供的HTML，input就在那里，可以直接 set_files
                    
                    await self.page.set_input_files(file_input_selector, image_paths)
                    logger.info("已设置上传文件")
                    
                    # 等待上传处理（文件显示在列表中）
                    await asyncio.sleep(2)
                    
                    # 点击"直接使用"按钮
                    use_directly_btn = self.page.locator('.ant-modal-content button.ant-btn-primary').filter(has_text='直接使用')
                    await use_directly_btn.wait_for(state='visible', timeout=10000)
                    await use_directly_btn.click()
                    logger.info("已点击【直接使用】按钮")
                    
                    # 等待模态框消失，图片加载到编辑器
                    await self.page.wait_for_selector('.ant-modal-content', state='hidden', timeout=10000)
                    logger.info("上传对话框已关闭，图片已加载")
                    
                    # 等待图片处理/加载完成
                    await asyncio.sleep(3) 

                except Exception as upload_err:
                    logger.error(f"图片上传失败: {upload_err}")
                    # 尝试截图
                    try:
                        await self.page.screenshot(path="upload_error.png")
                    except: pass
                    return None


            # 等待 textarea 出现并可见
            # 根据模式选择不同的 textarea
            if self.mode == "image_edit":
                textarea_selector = 'textarea[placeholder="请输入图片编辑指令"]'
            else:
                textarea_selector = 'textarea[placeholder="请输入提示词"]'
                
            await self.page.wait_for_selector(
                textarea_selector,
                state='visible',
                timeout=10000
            )
            logger.info("找到输入框")
            
            # 等待一小段时间确保元素稳定
            await asyncio.sleep(0.5)
            
            # 清空并输入提示词（使用 page.fill 而不是 element.fill）
            await self.page.fill(textarea_selector, '')  # 先清空
            await asyncio.sleep(0.2)
            await self.page.fill(textarea_selector, prompt)  # 再输入
            logger.info(f"已输入提示词: {prompt}")
            
            # 等待一小段时间确保输入完成
            await asyncio.sleep(0.5)
            
            # 点击"开始生图"按钮
            button_selector = 'button.muse-generate-button'
            await self.page.wait_for_selector(
                button_selector,
                state='visible',
                timeout=5000
            )
            
            # 使用 page.click 而不是 element.click
            await self.page.click(button_selector)
            logger.info("已点击开始生图按钮")
            
            # 等待弹出对话框并点击"无水印生成"
            try:
                # 等待对话框中的"无水印生成"按钮出现
                watermark_free_selector = 'div.muse-generationMethodCard-button'
                await self.page.wait_for_selector(
                    watermark_free_selector,
                    state='visible',
                    timeout=5000
                )
                logger.info("检测到生成方式选择对话框")
                
                # 点击"无水印生成"
                await self.page.click(watermark_free_selector)
                logger.info("已点击无水印生成")
                
                # 等待对话框关闭
                await asyncio.sleep(1)
                
            except Exception as dialog_error:
                # 如果没有对话框或对话框处理失败，记录但继续
                logger.warning(f"处理生成方式对话框时出错（可能不存在）: {dialog_error}")
            
            # 等待图片生成完成
            # 等待 successArea 出现
            success_area_selector = 'div.successArea'
            await self.page.wait_for_selector(
                success_area_selector,
                state='visible',
                timeout=timeout
            )
            logger.info("检测到生成成功")
            
            # 获取图片 URL
            img_selector = 'div.successArea img.image'
            await self.page.wait_for_selector(
                img_selector,
                state='visible',
                timeout=5000
            )
            
            # 使用 page.get_attribute 获取图片 URL
            image_url = await self.page.get_attribute(img_selector, 'src')
            logger.info(f"图片生成成功: {image_url}")
            
            return image_url
            
        except Exception as e:
            logger.error(f"生成图片失败: {e}")
            # 保存截图用于调试
            try:
                screenshot_path = f"debug_screenshot_{int(asyncio.get_event_loop().time())}.png"
                await self.page.screenshot(path=screenshot_path)
                logger.info(f"已保存调试截图: {screenshot_path}")
            except:
                pass
            return None

    
    async def save_cookies_and_storage(self, filepath: str = "data/modelscope_session.json"):
        """
        保存当前的 cookies 和 localStorage
        
        Args:
            filepath: 保存文件路径
        """
        try:
            cookies = await self.context.cookies()
            storage = await self.page.evaluate("() => Object.assign({}, localStorage)")
            
            session_data = {
                "cookies": cookies,
                "localStorage": storage
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"会话数据已保存到: {filepath}")
            
        except Exception as e:
            logger.error(f"保存会话数据失败: {e}")
    
    async def load_cookies_and_storage(self, filepath: str = "data/modelscope_session.json"):
        """
        从文件加载 cookies 和 localStorage
        
        Args:
            filepath: 会话文件路径
        """
        try:
            if not os.path.exists(filepath):
                logger.warning(f"会话文件不存在: {filepath}")
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 更新 cookies 和 localStorage
            self.cookies = session_data.get("cookies", [])
            self.local_storage = session_data.get("localStorage", {})
            
            logger.info(f"会话数据已从 {filepath} 加载")
            return True
            
        except Exception as e:
            logger.error(f"加载会话数据失败: {e}")
            return False


def check_environment():
    """
    检查当前环境是否适合运行 ModelScope 图片生成
    返回诊断信息和建议
    """
    issues = []
    warnings = []
    info = []
    
    # 检查操作系统
    os_name = platform.system()
    info.append(f"操作系统: {os_name} {platform.release()}")
    
    # 检查 Python 版本
    python_version = platform.python_version()
    info.append(f"Python 版本: {python_version}")
    
    # 检查 Playwright 是否已安装
    try:
        import playwright
        info.append(f"Playwright: 已安装")
    except ImportError:
        issues.append("❌ Playwright 未安装，请运行: pip install playwright")
        issues.append("   然后运行: python -m playwright install chromium")
    
    # Linux 特定检查
    if os_name == "Linux":
        # 检查 /dev/shm 大小
        try:
            stat = shutil.disk_usage('/dev/shm')
            shm_size_mb = stat.total / (1024 * 1024)
            if shm_size_mb < 64:
                warnings.append(f"⚠️  /dev/shm 空间较小 ({shm_size_mb:.0f}MB)，可能导致浏览器崩溃")
                warnings.append("   建议增加: sudo mount -o remount,size=512M /dev/shm")
            else:
                info.append(f"/dev/shm 空间: {shm_size_mb:.0f}MB ✓")
        except:
            warnings.append("⚠️  无法检查 /dev/shm 空间")
        
        # 检查必要的系统库（简化检查）
        required_libs = ['libnss3', 'libgbm1']
        missing_libs = []
        for lib in required_libs:
            if os.system(f"ldconfig -p | grep {lib} > /dev/null 2>&1") != 0:
                missing_libs.append(lib)
        
        if missing_libs:
            warnings.append(f"⚠️  可能缺少系统库: {', '.join(missing_libs)}")
            warnings.append("   请参考 docs/modelscope_server_setup.md 安装依赖")
    
    # 检查网络（简单ping测试）
    info.append("网络检查: 请确保可以访问 https://www.modelscope.cn")
    
    # 打印报告
    print("\n" + "="*60)
    print("ModelScope 环境诊断报告")
    print("="*60)
    
    if info:
        print("\n📋 环境信息:")
        for item in info:
            print(f"  {item}")
    
    if warnings:
        print("\n⚠️  警告:")
        for item in warnings:
            print(f"  {item}")
    
    if issues:
        print("\n❌ 问题:")
        for item in issues:
            print(f"  {item}")
        print("\n建议: 解决上述问题后再运行")
        return False
    
    if not warnings:
        print("\n✅ 环境检查通过!")
    else:
        print("\n⚠️  存在警告，但可以尝试运行")
    
    print("="*60 + "\n")
    return True


async def test_image_edit():
    """测试图像编辑"""
    generator = ModelScopeImageGenerator(headless=False, mode="image_edit")
    
    try:
        await generator.initialize()
        
        # 测试图像编辑
        prompt = "将图片中的女孩的头发改为红色"
        image_path = os.path.abspath("test.png")
        
        if not os.path.exists(image_path):
            print(f"Error: 测试图片不存在 {image_path}")
            return

        print(f"开始测试图像编辑，图片: {image_path}, 提示词: {prompt}")
        image_url = await generator.generate_image(prompt, image_paths=[image_path])
        
        if image_url:
            print(f"生成成功！图片 URL: {image_url}")
        else:
            print("生成失败")
        
        # 保存会话
        await generator.save_cookies_and_storage()
        
        # 等待一段时间以便查看结果
        await asyncio.sleep(10)
        
    finally:
        await generator.close()


if __name__ == "__main__":
    import warnings
    import sys
    
    # 在 Windows 上抑制 asyncio 清理时的无害警告
    if sys.platform == 'win32':
        warnings.filterwarnings('ignore', category=ResourceWarning, message='unclosed.*')
    
    logging.basicConfig(level=logging.INFO)
    
    # 运行环境检查
    print("正在检查运行环境...")
    if check_environment():
        print("开始测试...\n")
        # asyncio.run(test_generate())
        asyncio.run(test_image_edit())
    else:
        print("环境检查未通过，请先解决上述问题。")
        sys.exit(1)
