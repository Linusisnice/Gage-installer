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
import re

# Path to the aria2 executable
ARIA2_PATH = os.path.join(os.getcwd(), 'aria2c.exe')

# Global variables
download_queue = []
current_gid = None
server = None
aria2_process = None
total_files_length = 0  # Total length of all files
completed_length = 0  # Completed length of all downloads
metadata_downloaded = False  # Flag to track if metadata has been downloaded
console_window = None  # The console window

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
        # Find all download sections (supporting variations)
        download_section_titles = ["Download Mirrors", "Download", "Direct Links", "Torrent", "Direct Links (Torrent)", "Download Mirrors (Direct Links)", "Download Mirrors (Torrent)", "Links", "Mirror", "Mirrors"]
        download_sections = []
        magnet_links = set()  # Use set to avoid duplicate magnet links

        # Search for section headers and find their corresponding links
    for title in download_section_titles:
        section = soup.find('h2', text=re.compile(title, re.IGNORECASE))
        if section:
            download_container = section.find_parent().find_next_sibling()            
            if download_container:
                # Extract all links from the section
                links = download_container.find_all('a', href=True)
                for link in links:
                    href = link['href']
                    text = link.text.strip()
                    # Add non-magnet links to the download sections
                    if not href.startswith('magnet:') and 'jdownloader' not in text.lower():
                        download_sections.append((text, href))
                    # Add magnet links to the magnet set to avoid duplicates
                    elif href.startswith('magnet:'):
                        magnet_links.add(href)

    # Find the "Popular Repacks" section
    popular_repacks_section = soup.find('a', href=True, text=re.compile("Popular Repacks", re.IGNORECASE))
    if popular_repacks_section:
        popular_repacks_index = next((i for i, (text, href) in enumerate(download_sections) if text == popular_repacks_section.text.strip()), None)
        if popular_repacks_index is not None:
            # Remove all links below the "Popular Repacks" link
            download_sections = download_sections[:popular_repacks_index]

        # Additionally, search for links within <ul> elements
        ul_elements = soup.find_all('ul')
        for ul in ul_elements:
            links = ul.find_all('a', href=True)
            for link in links:
                href = link['href']
                text = link.text.strip()
                # Add non-magnet links to the download sections
                if not href.startswith('magnet:') and 'jdownloader' not in text.lower():
                    download_sections.append((text, href))
                # Add magnet links to the magnet set to avoid duplicates
                elif href.startswith('magnet:'):
                    magnet_links.add(href)

        # Convert magnet links set to list and add them to download sections with proper labels
        for magnet_link in magnet_links:
            download_sections.append(("Magnet Link", magnet_link))

        # Return all collected links from various sections
        return download_sections if download_sections else None

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
            result_label.bind("<Button-1>", lambda _, url=link: display_download_links(url))
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

def openconsole():
    global console_window, aria2_output

    if console_window is not None:
        console_window.lift()
        return

    console_window = tk.Toplevel(root)
    console_window.title("Console Output")
    console_window.geometry("800x400")

    console_text = tk.Text(console_window, wrap=tk.WORD)
    console_text.pack(expand=True, fill=tk.BOTH)

    def update_console():
        while True:
            if aria2_output:
                console_text.insert(tk.END, aria2_output + "\n")
                console_text.see(tk.END)
            time.sleep(1)

    console_thread = threading.Thread(target=update_console, daemon=True)
    console_thread.start()
# Function to start the next download in the queue
def start_next_download():
    global current_gid, server, total_files_length, completed_length, aria2_process, metadata_downloaded
    total_files_length = 0
    completed_length = 0
    metadata_downloaded = False  # Reset the metadata download flag

    if not download_queue:
        messagebox.showinfo("Queue", "No downloads left in the queue.")
        return

    magnet_link = download_queue[0]

    try:
        # Start aria2c with --seed-time=0 to prevent seeding
        aria2_process = subprocess.Popen([ARIA2_PATH, '--enable-rpc', '--rpc-listen-all=false', '--rpc-listen-port=6800', '--dir=./downloads', '--seed-time=0'],
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=True)

        server = xmlrpc.client.ServerProxy('http://localhost:6800/rpc')
        current_gid = server.aria2.addUri([magnet_link])

        # Start the download progress tracking in a new thread
        download_thread = threading.Thread(target=track_download_progress, args=(server, current_gid))
        download_thread.start()

        # Start monitoring the console output in another thread
        console_thread = threading.Thread(target=update_console_output, args=(aria2_process,))
        console_thread.start()

    except Exception as e:
        messagebox.showerror("Error", f"Failed to start download: {e}")

# Function to update the console window and track progress for the progress bar
def update_console_output(process):
    global aria2_output, metadata_downloaded
    while True:
        line = process.stdout.readline()
        if not line:
            break

        # Capture output from aria2c and look for percentages
        aria2_output = line.strip()
        print(aria2_output)  # Print to console (useful for debugging)

        # Extract percentage from the line and update progress bar
        match = re.search(r'(\d+)%', aria2_output)
        if match:
            percentage = int(match.group(1))
            progress_bar['value'] = percentage
            progress_label.config(text=f"Downloading: {percentage}%")

        # Detect the "Your share ratio was" line to mark completion
        if "Download complete" in aria2_output:
            if metadata_downloaded==True:  # Only open the folder after the actual data download is completed
                progress_bar['value'] = 100
                progress_label.config(text="Download complete!")
                open_newest_folder(os.path.join(os.getcwd(), 'downloads'))  # Open the newly created folder
                metadata_downloaded = False  # Reset the metadata download flag
                break
            else:
                metadata_downloaded = True  # Mark metadata as downloaded and ignore opening the folder

        root.update_idletasks()
completed_download = 0
# Function to track download progress (placeholder as progress bar is updated from console output)
def track_download_progress(server, gid):
    cancel_button.config(state=tk.NORMAL)

    while True:
        try:
            status = server.aria2.tellStatus(gid)

            # Check if the download is complete
            if status['status'] == 'complete':
                if completed_download==1:
                    progress_label.config(text="Download complete!")
                    progress_bar['value'] = 100
                    if metadata_downloaded:  # Ensure folder is opened after actual data download completes
                        open_newest_folder(os.path.join(os.getcwd(), 'downloads'))
                    break
                else:
                    completed_download = 1
                    break

            root.update_idletasks()

        except Exception as e:
            print(f"Error tracking progress: {e}")
            break

        time.sleep(1)

# Function to open the newest folder in a given parent folder
def open_newest_folder(parent_folder):
    # Get the list of folders in the parent folder
    folders = [os.path.join(parent_folder, d) for d in os.listdir(parent_folder) if os.path.isdir(os.path.join(parent_folder, d))]

    if not folders:
        print("No folders found.")
        return

    # Find the newest folder by comparing creation times
    newest_folder = max(folders, key=os.path.getctime)

    # Print the name of the newest folder for reference
    print(f"Newest folder: {newest_folder}")

    # Open the newest folder
    subprocess.Popen(f'explorer "{newest_folder}"')

# Function to pause or resume the current download


# Function to cancel the current download
# def cancel_download():
#     global server, current_gid
#     try:
#         server.aria2.remove(current_gid)
#         download_queue.pop(0)
#         shutil.rmtree('./downloads', ignore_errors=True)
#         progress_label.config(text="Download canceled and files removed.")
#         progress_bar['value'] = 0
#         pause_button.config(state=tk.DISABLED)
#         cancel_button.config(state=tk.DISABLED)
#         update_queue_display()
#         start_next_download()
#     except Exception as e:
#         messagebox.showerror("Error", f"Failed to cancel download: {e}")
#         # Function to kill aria2c.exe and delete the newest folder within the downloads folder
def cancel_download():
    global aria2_process

    # Kill aria2c.exe process
    if aria2_process:
        aria2_process.terminate()
        aria2_process.wait()
        aria2_process = None
    progress_label.config(text="Download canceled.")
    progress_bar['value'] = 0
    # Ensure aria2c.exe is killed
    try:
        subprocess.run(["taskkill", "/F", "/IM", "aria2c.exe"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to kill aria2c.exe: {e}")

    # Delete the newest folder within the downloads folder
    downloads_folder = os.path.join(os.getcwd(), 'downloads')
    folders = [os.path.join(downloads_folder, d) for d in os.listdir(downloads_folder) if os.path.isdir(os.path.join(downloads_folder, d))]

    if folders:
        newest_folder = max(folders, key=os.path.getctime)
        shutil.rmtree(newest_folder, ignore_errors=True)
        print(f"Deleted folder: {newest_folder}")
    else:
        print("No folders found to delete.")

    # Delete the newest .aria2 file within the downloads folder
    aria2_files = [os.path.join(downloads_folder, f) for f in os.listdir(downloads_folder) if f.endswith('.aria2')]

    if aria2_files:
        newest_aria2_file = max(aria2_files, key=os.path.getctime)
        os.remove(newest_aria2_file)
        print(f"Deleted .aria2 file: {newest_aria2_file}")
    else:
        print("No .aria2 files found to delete.")
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
root.title("FitGirl Repacks Downloader")
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

cancel_button = tk.Button(root, text="Cancel", command=cancel_download, font=("Arial", 12, "bold"), state=tk.DISABLED)
cancel_button.pack(side=tk.LEFT, padx=10, pady=10)

console_button = tk.Button(root, text="Show logs", command=openconsole, font=("Arial", 12, "bold"))
console_button.pack(side=tk.LEFT, padx=5, pady=5)

queue_frame = tk.Frame(root, bg="lightblue")
queue_frame.pack(pady=10)

queue_button = tk.Button(root, text="Show Queue", command=update_queue_display, font=("Arial", 12, "bold"))
queue_button.pack(pady=10)

root.mainloop()
