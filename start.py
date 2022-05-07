import iKuai
import asyncio

helper = iKuai.iKuaiHelper()
# helper.acl_mac("clear")
# quit()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    tasks = [
        asyncio.ensure_future(helper.periodicTasks()),
    ]
    try:
        loop.run_until_complete(asyncio.wait(tasks))
    except KeyboardInterrupt as e:
        print("Caught keyboard interrupt. Canceling tasks...")
        helper.on_exit()