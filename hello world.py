import os
import subprocess
import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import messagebox, Menu
import threading
import webbrowser
from tkinter import ttk
import xmlrpc.client
import time
import shutil

# Path to the aria2 executable
ARIA2_PATH = os.path.join(os.getcwd(), 'aria2c.exe')

# Global variables
download_queue = []
current_gid = None
server = None
total_files_length = 0  # Total length of all files
completed_length = 0  # Completed length of all downloads

# Function to fetch search results
def fetch_search_results(query):
    url = f'https://fitgirl-repacks.site/?s={query}'
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        search_results = soup.find_all('article', class_='post')
        results = [(result.find('h1', class_='entry-title').text.strip(), result.find('h1', class_='entry-title').find('a')['href']) for result in search_results]
        return results
    else:
        messagebox.showerror("Error", f"Failed to retrieve search results. Status code: {response.status_code}")
        return []

# Function to fetch download links
def fetch_download_links(page_url):
    response = requests.get(page_url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        download_section = soup.find(text="Download Mirrors")
        if download_section:
            download_container = download_section.find_parent().find_next_sibling()
            download_links = [(a.text.strip(), a['href']) for a in download_container.find_all('a', href=True) if 'jdownloader' not in a.text.lower()]
            return download_links
        else:
            messagebox.showinfo("Info", "No download mirrors found.")
            return []
    else:
        messagebox.showerror("Error", f"Failed to retrieve download links. Status code: {response.status_code}")
        return []

# Function to display search results
def display_results():
    query = search_entry.get()
    if not query:
        messagebox.showwarning("Input Error", "Please enter a search term.")
        return

    results = fetch_search_results(query)
    for widget in results_frame.winfo_children():
        widget.destroy()

    if results:
        for title, link in results:
            result_label = tk.Label(results_frame, text=title, fg="blue", cursor="hand2", wraplength=600, font=("Arial", 12, "bold"))
            result_label.pack(anchor='w', pady=5)
            result_label.bind("<Button-1>", lambda e, url=link: display_download_links(url))
    else:
        tk.Label(results_frame, text="No results found.", fg="red", font=("Arial", 12, "italic")).pack(anchor='w')

# Function to display download links
def display_download_links(url):
    download_links = fetch_download_links(url)
    for widget in results_frame.winfo_children():
        widget.destroy()

    magnet_links = []
    non_magnet_links = []

    if download_links:
        for text, link in download_links:
            if link.startswith('magnet:'):
                magnet_links.append((text, link))
            else:
                non_magnet_links.append((text, link))

        for text, link in magnet_links:
            tk.Button(results_frame, text=f"Download {text}", fg="white", bg="green", cursor="hand2", font=("Arial", 10, "bold"), command=lambda url=link: add_to_queue(url)).pack(anchor='w', pady=5, padx=10, fill='x')

        if non_magnet_links:
            dropdown_button = tk.Menubutton(results_frame, text="Show Other Links", relief="raised", bg="lightgray", cursor="hand2", font=("Arial", 10, "bold"))
            dropdown_button.menu = Menu(dropdown_button, tearoff=0)
            dropdown_button["menu"] = dropdown_button.menu
            for text, link in non_magnet_links:
                dropdown_button.menu.add_command(label=f"{text}: {link}", command=lambda url=link: open_link(url))
            dropdown_button.pack(anchor='w', pady=5, padx=10)

    else:
        tk.Label(results_frame, text="No download links found.", fg="red", font=("Arial", 12, "italic")).pack(anchor='w')

# Function to add download to queue
def add_to_queue(magnet_link):
    download_queue.append(magnet_link)
    messagebox.showinfo("Queued", "The torrent has been added to the queue.")
    if len(download_queue) == 1:
        start_next_download()
    update_queue_display()

# Function to start the next download in the queue
def start_next_download():
    global current_gid, server, total_files_length, completed_length
    total_files_length = 0
    completed_length = 0

    if not download_queue:
        messagebox.showinfo("Queue", "No downloads left in the queue.")
        return

    magnet_link = download_queue[0]

    try:
        subprocess.Popen([ARIA2_PATH, '--enable-rpc', '--rpc-listen-all=false', '--rpc-listen-port=6800', '--dir=./downloads'], shell=True)
        time.sleep(2)  # Allow time for aria2c to start

        server = xmlrpc.client.ServerProxy('http://localhost:6800/rpc')
        current_gid = server.aria2.addUri([magnet_link])

        download_thread = threading.Thread(target=track_download_progress, args=(server, current_gid))
        download_thread.start()

    except Exception as e:
        messagebox.showerror("Error", f"Failed to start download: {e}")

# Function to track download progress
def track_download_progress(server, gid):
    global total_files_length, completed_length
    pause_button.config(state=tk.NORMAL)
    cancel_button.config(state=tk.NORMAL)

    while True:
        try:
            status = server.aria2.tellStatus(gid)
            files = server.aria2.getFiles(gid)

            if not total_files_length:
                # Calculate total length of all files after metadata download
                total_files_length = sum(int(f['length']) for f in files if int(f['length']) > 0)

            completed_length = sum(int(f['completedLength']) for f in files)

            # Check if the download is complete
            if status['status'] == 'complete':
                progress_label.config(text="Download complete!")
                progress_bar['value'] = 100
                break

            # Update progress based on all files
            progress = (completed_length / total_files_length) * 100
            progress_bar['value'] = progress
            progress_label.config(text=f"Downloading: {int(progress)}% ({completed_length / (1024**2):.2f} MB / {total_files_length / (1024**2):.2f} MB)")

            root.update_idletasks()

        except Exception as e:
            print(f"Error tracking progress: {e}")
            break

        time.sleep(1)

# Function to pause or resume the current download
def pause_download():
    global server, current_gid
    try:
        if pause_button['text'] == 'Pause':
            server.aria2.pause(current_gid)
            pause_button.config(text='Resume')
        else:
            server.aria2.unpause(current_gid)
            pause_button.config(text='Pause')
    except Exception as e:
        messagebox.showerror("Error", f"Failed to pause/resume download: {e}")

# Function to cancel the current download
def cancel_download():
    global server, current_gid
    try:
        server.aria2.remove(current_gid)
        download_queue.pop(0)
        shutil.rmtree('./downloads', ignore_errors=True)
        progress_label.config(text="Download canceled and files removed.")
        progress_bar['value'] = 0
        pause_button.config(state=tk.DISABLED)
        cancel_button.config(state=tk.DISABLED)
        update_queue_display()
        start_next_download()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to cancel download: {e}")

# Function to open non-magnet links in the browser
def open_link(url):
    webbrowser.open_new_tab(url)

# Function to update the queue display
def update_queue_display():
    for widget in queue_frame.winfo_children():
        widget.destroy()

    if download_queue:
        queue_label = tk.Label(queue_frame, text="Current Download Queue:", font=("Arial", 12, "bold"), bg="lightblue")
        queue_label.pack(anchor='w')

        for idx, magnet_link in enumerate(download_queue):
            tk.Label(queue_frame, text=f"{idx+1}. {magnet_link[:50]}...", font=("Arial", 10), bg="lightblue").pack(anchor='w')
    else:
        queue_label = tk.Label(queue_frame, text="Queue is empty.", font=("Arial", 12, "italic"), bg="lightblue")
        queue_label.pack(anchor='w')

# Main UI setup
root = tk.Tk()
root.title("FitGirl Repacks Search")
root.geometry("800x600")
root.configure(bg="lightblue")

search_frame = tk.Frame(root, bg="lightblue")
search_frame.pack(pady=20)

search_label = tk.Label(search_frame, text="Search:", font=("Arial", 14, "bold"), bg="lightblue")
search_label.pack(side=tk.LEFT, padx=5)

search_entry = tk.Entry(search_frame, width=50, font=("Arial", 14))
search_entry.pack(side=tk.LEFT, padx=5)

search_button = tk.Button(search_frame, text="Search", command=display_results, font=("Arial", 12, "bold"), bg="green", fg="white", cursor="hand2")
search_button.pack(side=tk.LEFT, padx=5)

results_frame = tk.Frame(root, bg="white")
results_frame.pack(pady=10, fill=tk.BOTH, expand=True)

progress_bar = ttk.Progressbar(root, orient=tk.HORIZONTAL, length=500, mode='determinate')
progress_bar.pack(pady=10)

progress_label = tk.Label(root, text="", font=("Arial", 12, "italic"), bg="lightblue")
progress_label.pack()

pause_button = tk.Button(root, text="Pause", command=pause_download, font=("Arial", 12, "bold"), state=tk.DISABLED)
pause_button.pack(side=tk.LEFT, padx=10, pady=10)

cancel_button = tk.Button(root, text="Cancel", command=cancel_download, font=("Arial", 12, "bold"), state=tk.DISABLED)
cancel_button.pack(side=tk.LEFT, padx=10, pady=10)

queue_frame = tk.Frame(root, bg="lightblue")
queue_frame.pack(pady=10)

queue_button = tk.Button(root, text="Show Queue", command=update_queue_display, font=("Arial", 12, "bold"))
queue_button.pack(pady=10)

root.mainloop()
